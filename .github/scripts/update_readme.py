# update_readme.py
import os
import requests
import json
from datetime import datetime, timezone, timedelta
import re
from collections import defaultdict, Counter
from dotenv import load_dotenv

load_dotenv()  # Load .env file
token = os.environ.get('GITHUB_TOKEN')

class GitHubReadmeUpdater:
    def __init__(self):
        self.token = token
        self.username = os.environ.get('USERNAME', 'kri-hika')
        
        # Use authentication if token is available, else use public API
        if self.token:
            self.headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json'
            }
        else:
            self.headers = {
                'Accept': 'application/vnd.github.v3+json'
            }
        
        self.base_url = 'https://api.github.com'

    def make_request(self, url, params=None):
        """Make API request with error handling"""
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API request failed: {e}")
            return None

    def get_user_stats(self):
        """Get basic user statistics"""
        user_data = self.make_request(f"{self.base_url}/users/{self.username}")
        if not user_data:
            return {}
        
        return {
            'followers': user_data.get('followers', 0),
            'following': user_data.get('following', 0),
            'public_repos': user_data.get('public_repos', 0),
            'created_at': user_data.get('created_at', '')
        }

    def get_all_repositories(self):
        """Get all repositories including collaborations and forks"""
        all_repos = []
        page = 1
        
        while True:
            # Use different endpoints based on authentication
            if self.token:
                # Authenticated: get all repos including collaborations
                repos_data = self.make_request(
                    f"{self.base_url}/user/repos",
                    params={
                        'visibility': 'all',
                        'affiliation': 'owner,collaborator,organization_member',
                        'sort': 'updated',
                        'per_page': 100,
                        'page': page
                    }
                )
            else:
                # Public API: get only public repos
                repos_data = self.make_request(
                    f"{self.base_url}/users/{self.username}/repos",
                    params={
                        'sort': 'updated',
                        'per_page': 100,
                        'page': page
                    }
                )
            
            if not repos_data or len(repos_data) == 0:
                break
                
            all_repos.extend(repos_data)
            page += 1
            
            # Safety break to avoid infinite loops
            if page > 20:  # Increased limit for more repos
                break
        
        return all_repos

    def calculate_repository_stats(self, repos):
        """Calculate accurate repository statistics including collaborations"""
        if not repos:
            return {}
        
        public_repos = [r for r in repos if not r.get('private', True)]
        private_repos = [r for r in repos if r.get('private', False)]
        own_repos = [r for r in repos if not r.get('fork', False)]
        forked_repos = [r for r in repos if r.get('fork', False)]
        # Better collaboration detection - repos where you're not the owner but have contributed
        collaborated_repos = []
        for repo in repos:
            # If you're not the owner and it's not a fork, it's likely a collaboration
            if (repo.get('owner', {}).get('login') != self.username and 
                not repo.get('fork', False) and 
                repo.get('permissions')):
                collaborated_repos.append(repo)
        
        # Count stars from all public repos (including collaborations)
        total_stars = sum(repo.get('stargazers_count', 0) for repo in public_repos)
        total_forks = sum(repo.get('forks_count', 0) for repo in public_repos)
        
        # Language statistics from all repos (by repository count)
        languages = Counter()
        for repo in repos:
            if repo.get('language'):
                languages[repo['language']] += 1
        
        return {
            'public_repos': len(public_repos),
            'private_repos': len(private_repos),
            'total_repos': len(repos),
            'own_repos': len(own_repos),
            'forked_repos': len(forked_repos),
            'collaborated_repos': len(collaborated_repos),
            'total_stars': total_stars,
            'total_forks': total_forks,
            'top_languages': [lang for lang, _ in languages.most_common(4)]
        }

    def get_contributed_repos_graphql(self):
        """Get all repositories the user has contributed to using the GitHub GraphQL API (all-time)"""
        url = 'https://api.github.com/graphql'
        headers = {
            'Authorization': f'bearer {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        query = '''
        query($login: String!, $after: String) {
          user(login: $login) {
            contributionsCollection {
              contributionYears
            }
            repositoriesContributedTo(first: 100, after: $after, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY], includeUserRepositories: true) {
              totalCount
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                nameWithOwner
              }
            }
          }
        }
        '''
        # Get all pages
        contributed_repos = set()
        after = None
        while True:
            variables = {"login": self.username, "after": after}
            response = requests.post(url, headers=headers, json={"query": query, "variables": variables})
            if response.status_code != 200:
                break
            data = response.json()
            repos = data['data']['user']['repositoriesContributedTo']['nodes']
            for repo in repos:
                contributed_repos.add(repo['nameWithOwner'])
            page_info = data['data']['user']['repositoriesContributedTo']['pageInfo']
            if not page_info['hasNextPage']:
                break
            after = page_info['endCursor']
        return len(contributed_repos)

    def get_contribution_statistics(self):
        """Get real contribution statistics from events API and GraphQL API"""
        events_data = self.make_request(
            f"{self.base_url}/users/{self.username}/events",
            params={'per_page': 100}
        )
        
        # Use GraphQL for total contributed repos (all-time)
        total_contributions = self.get_contributed_repos_graphql()
        
        if not events_data:
            return {}
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        year_ago = now - timedelta(days=365)
        
        weekly_commits = 0
        monthly_commits = 0
        yearly_commits = 0
        weekly_repos = set()
        monthly_repos = set()
        day_activity = defaultdict(int)
        hour_activity = defaultdict(int)
        
        for event in events_data:
            event_date = datetime.fromisoformat(event['created_at'].replace('Z', '+00:00'))
            
            if event['type'] == 'PushEvent':
                commits = event.get('payload', {}).get('commits', [])
                commit_count = len(commits)
                repo_name = event.get('repo', {}).get('name', '')
                
                if event_date >= week_ago:
                    weekly_commits += commit_count
                    weekly_repos.add(repo_name)
                
                if event_date >= month_ago:
                    monthly_commits += commit_count
                    monthly_repos.add(repo_name)
                
                if event_date >= year_ago:
                    yearly_commits += commit_count
                    day_activity[event_date.strftime('%A')] += commit_count
                    hour_activity[event_date.hour] += commit_count
        
        # Find most active day and hour
        most_active_day = max(day_activity.items(), key=lambda x: x[1])[0] if day_activity else "Unknown"
        most_active_hours = sorted(hour_activity.items(), key=lambda x: x[1], reverse=True)[:2]
        peak_hours = f"{most_active_hours[0][0]}:00" if most_active_hours else "Unknown"
        
        return {
            'weekly_commits': weekly_commits,
            'monthly_commits': monthly_commits,
            'yearly_commits': yearly_commits,
            'weekly_repos': len(weekly_repos),
            'monthly_repos': len(monthly_repos),
            'most_active_day': most_active_day,
            'peak_hours': peak_hours,
            'total_events': len(events_data),
            'total_contributions': total_contributions
        }

    def get_profile_views(self):
        """Get profile view count (requires external service or manual tracking)"""
        # GitHub doesn't provide profile view API
        # You'd need to integrate with services like:
        # - komarev.com/ghpvc (view counter badge service)
        # - hits.seeyoufarm.com
        # - custom analytics
        
        # For now, return a placeholder that indicates this needs external setup
        return "External counter needed"

    def calculate_language_percentages(self, repos):
        """Calculate actual language percentages from repository data"""
        if not repos:
            return "No data available"
        
        # Get language bytes for each repo (requires additional API calls)
        language_bytes = defaultdict(int)
        
        for repo in repos[:10]:  # Limit to avoid API rate limits
            if not repo.get('fork', False):  # Only count own repos
                lang_data = self.make_request(f"{self.base_url}/repos/{repo['full_name']}/languages")
                if lang_data:
                    for lang, bytes_count in lang_data.items():
                        language_bytes[lang] += bytes_count
        
        if not language_bytes:
            return "No data available"
        
        total_bytes = sum(language_bytes.values())
        percentages = []
        
        for lang, bytes_count in sorted(language_bytes.items(), key=lambda x: x[1], reverse=True)[:4]:
            percentage = round((bytes_count / total_bytes) * 100, 1)
            percentages.append(f"{lang} ({percentage}%)")
        
        return ", ".join(percentages)

    def generate_stats_section(self, user_stats, repo_stats, contributions):
        """Generate accurate stats section in table format for At a Glance"""
        repo_count = repo_stats.get('total_repos', 0)
        star_count = repo_stats.get('total_stars', 0)
        commit_count = contributions.get('yearly_commits', 0)
        top_lang = repo_stats.get('top_languages', ['-'])[0] if repo_stats.get('top_languages') else '-'

        section = "### 📊 At a Glance\n\n"
        section += "<table>\n<tr>\n"
        section += f'<td align="center"><strong>{repo_count}</strong><br/><sub>📁 Repos</sub></td>\n'
        section += f'<td align="center"><strong>{star_count}</strong><br/><sub>⭐ Stars</sub></td>\n'
        section += f'<td align="center"><strong>{commit_count}</strong><br/><sub>📝 Commits</sub></td>\n'
        section += f'<td align="center"><strong>{top_lang}</strong><br/><sub>🎨 Top Lang</sub></td>\n'
        section += "</tr>\n</table>\n\n"
        section += "<sub>*Live stats • Updated every 6hrs*</sub>\n"
        return section

    def generate_activity_section(self, repo_stats, contributions, repos):
        """Generate accurate development activity section"""
        section = "## 🚀 Recent Development Activity (Auto-Updated)\n\n"
        
        # Contribution Overview
        section += "### 📈 **Contribution Overview**\n"
        section += f"- **This Week:** {contributions.get('weekly_commits', 0)} commits across {contributions.get('weekly_repos', 0)} repositories\n"
        section += f"- **This Month:** {contributions.get('monthly_commits', 0)} commits (including private repos)\n"
        section += f"- **This Year:** {contributions.get('yearly_commits', 0)} total commits\n"
        
        # Language info is already shown in GitHub Wrapped section
        # section += f"- **Languages Used:** {lang_percentages}\n\n"
        
        # GitHub Achievements
        section += "### 🏆 **GitHub Achievements**\n"
        section += f"- 🎯 **Total Contributions:** {contributions.get('yearly_commits', 0)} (2024)\n"
        section += f"- 📁 **Repository Activity:** {repo_stats.get('public_repos', 0)} public, {repo_stats.get('private_repos', 0)} private repositories\n"
        section += f"- 🔥 **Most Productive Day:** {contributions.get('most_active_day', 'Unknown')}\n"
        section += f"- ⭐ **Community Impact:** {repo_stats.get('total_stars', 0)} stars received, {repo_stats.get('total_forks', 0)} repositories forked\n\n"
        
        # Development Patterns
        section += "### 📊 **Development Patterns**\n"
        section += f"- **Peak Coding Hours:** Around {contributions.get('peak_hours', 'Unknown')}\n"
        section += f"- **Most Active Day:** {contributions.get('most_active_day', 'Unknown')}\n"
        section += f"- **Monthly Repository Activity:** {contributions.get('monthly_repos', 0)} different repositories\n"
        section += f"- **Recent Event Activity:** {contributions.get('total_events', 0)} total events tracked\n\n"
        section += "---\n\n"
        
        return section

    def update_readme(self):
        """Main function to update README.md with real data"""
        print("🤖 Fetching real GitHub statistics...")
        
        # Fetch all data
        user_stats = self.get_user_stats()
        repos = self.get_all_repositories()
        repo_stats = self.calculate_repository_stats(repos)
        contributions = self.get_contribution_statistics()
        
        print(f"✅ Found {len(repos)} repositories")
        print(f"✅ {repo_stats.get('total_stars', 0)} total stars")
        print(f"✅ {contributions.get('yearly_commits', 0)} commits this year")
        
        # Read current README
        try:
            with open('README.md', 'r', encoding='utf-8') as file:
                readme_content = file.read()
        except FileNotFoundError:
            print("❌ README.md not found!")
            return
        
        # Generate new sections with real data
        new_stats_section = self.generate_stats_section(user_stats, repo_stats, contributions)
        new_activity_section = self.generate_activity_section(repo_stats, contributions, repos)
        
        # Update sections
        markers = {
            '<!-- STATS_START -->': '<!-- STATS_END -->',
            '<!-- PROJECTS_START -->': '<!-- PROJECTS_END -->'
        }
        
        sections = {
            '<!-- STATS_START -->': new_stats_section,
            '<!-- PROJECTS_START -->': new_activity_section
        }
        
        updated_content = readme_content
        
        for start_marker, end_marker in markers.items():
            if start_marker in sections and start_marker in updated_content and end_marker in updated_content:
                pattern = f"{re.escape(start_marker)}.*?{re.escape(end_marker)}"
                replacement = f"{start_marker}\n{sections[start_marker]}{end_marker}"
                updated_content = re.sub(pattern, replacement, updated_content, flags=re.DOTALL)
                print(f"✅ Updated section: {start_marker}")
        
        # Write updated README
        with open('README.md', 'w', encoding='utf-8') as file:
            file.write(updated_content)
        
        print("🎉 README.md updated with real GitHub statistics!")

if __name__ == "__main__":
    updater = GitHubReadmeUpdater()
    updater.update_readme()