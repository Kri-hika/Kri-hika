# update_readme.py
import os
import requests
import json
from datetime import datetime, timezone
import re

class GitHubReadmeUpdater:
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN')
        self.username = os.environ.get('USERNAME', 'kri-hika')
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        self.base_url = 'https://api.github.com'

    def get_recent_repos(self):
        """Get recently updated repositories"""
        url = f"{self.base_url}/users/{self.username}/repos"
        params = {
            'sort': 'updated',
            'direction': 'desc',
            'per_page': 10
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        repos = response.json()
        
        # Filter out forks and select top 5 recent projects
        recent_projects = []
        for repo in repos:
            if not repo['fork'] and not repo['archived']:
                recent_projects.append({
                    'name': repo['name'],
                    'description': repo['description'] or 'No description available',
                    'language': repo['language'] or 'Mixed',
                    'updated_at': repo['updated_at'],
                    'stars': repo['stargazers_count'],
                    'url': repo['html_url'],
                    'topics': repo['topics'][:3]  # First 3 topics
                })
                
                if len(recent_projects) >= 5:
                    break
        
        return recent_projects

    def get_recent_commits(self):
        """Get recent commit activity across repositories"""
        url = f"{self.base_url}/users/{self.username}/events"
        params = {'per_page': 30}
        
        response = requests.get(url, headers=self.headers, params=params)
        events = response.json()
        
        recent_commits = []
        for event in events:
            if event['type'] == 'PushEvent':
                for commit in event['payload']['commits'][:2]:  # Max 2 commits per push
                    recent_commits.append({
                        'repo': event['repo']['name'].split('/')[-1],
                        'message': commit['message'].split('\n')[0][:60] + '...' if len(commit['message']) > 60 else commit['message'],
                        'date': event['created_at']
                    })
                    
                    if len(recent_commits) >= 5:
                        break
            
            if len(recent_commits) >= 5:
                break
        
        return recent_commits

    def get_github_stats(self):
        """Get comprehensive GitHub statistics"""
        # Get user info
        user_url = f"{self.base_url}/users/{self.username}"
        user_response = requests.get(user_url, headers=self.headers)
        user_data = user_response.json()
        
        # Get repositories for additional stats
        repos_url = f"{self.base_url}/users/{self.username}/repos"
        repos_response = requests.get(repos_url, headers=self.headers, params={'per_page': 100})
        repos_data = repos_response.json()
        
        total_stars = sum(repo['stargazers_count'] for repo in repos_data if not repo['fork'])
        total_repos = len([repo for repo in repos_data if not repo['fork']])
        languages = {}
        
        for repo in repos_data:
            if not repo['fork'] and repo['language']:
                languages[repo['language']] = languages.get(repo['language'], 0) + 1
        
        top_languages = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:3]
        
        return {
            'followers': user_data['followers'],
            'following': user_data['following'],
            'total_repos': total_repos,
            'total_stars': total_stars,
            'top_languages': [lang[0] for lang in top_languages]
        }

    def generate_project_section(self, projects):
        """Generate the automated project showcase section"""
        section = "## 🚀 Latest Projects (Auto-Updated)\n\n"
        
        for i, project in enumerate(projects, 1):
            # Format last updated
            updated_date = datetime.fromisoformat(project['updated_at'].replace('Z', '+00:00'))
            days_ago = (datetime.now(timezone.utc) - updated_date).days
            
            if days_ago == 0:
                last_updated = "Updated today"
            elif days_ago == 1:
                last_updated = "Updated yesterday"
            else:
                last_updated = f"Updated {days_ago} days ago"
            
            # Format topics as badges
            topic_badges = " ".join([f"`{topic}`" for topic in project['topics']])
            
            section += f"### {i}. **{project['name']}** ⭐ {project['stars']}\n"
            section += f"*{project['description']}*\n\n"
            section += f"**Language:** {project['language']} | **{last_updated}**\n"
            if topic_badges:
                section += f"**Topics:** {topic_badges}\n"
            section += f"🔗 [View Project]({project['url']})\n\n"
            section += "---\n\n"
        
        return section

    def generate_activity_section(self, commits):
        """Generate recent activity section"""
        section = "## ⚡ Recent Activity (Auto-Updated)\n\n"
        section += "```\n"
        
        for commit in commits:
            commit_date = datetime.fromisoformat(commit['date'].replace('Z', '+00:00'))
            formatted_date = commit_date.strftime('%b %d')
            section += f"📝 {formatted_date} | {commit['repo']} | {commit['message']}\n"
        
        section += "```\n\n"
        section += f"*Last updated: {datetime.now().strftime('%B %d, %Y at %H:%M UTC')}*\n\n"
        
        return section

    def generate_stats_section(self, stats):
        """Generate dynamic stats section"""
        section = "## 📊 Live GitHub Stats\n\n"
        section += f"🔥 **{stats['total_repos']} repositories** | "
        section += f"⭐ **{stats['total_stars']} total stars** | "
        section += f"👥 **{stats['followers']} followers**\n\n"
        
        if stats['top_languages']:
            section += f"**Top Languages:** {' • '.join(stats['top_languages'])}\n\n"
        
        return section

    def update_readme(self):
        """Main function to update README.md"""
        print("🤖 Fetching latest GitHub data...")
        
        # Fetch data
        recent_projects = self.get_recent_repos()
        recent_commits = self.get_recent_commits()
        github_stats = self.get_github_stats()
        
        # Read current README
        try:
            with open('README.md', 'r', encoding='utf-8') as file:
                readme_content = file.read()
        except FileNotFoundError:
            print("❌ README.md not found!")
            return
        
        # Generate new sections
        new_projects_section = self.generate_project_section(recent_projects)
        new_activity_section = self.generate_activity_section(recent_commits)
        new_stats_section = self.generate_stats_section(github_stats)
        
        # Update sections with markers
        markers = {
            '<!-- PROJECTS_START -->': '<!-- PROJECTS_END -->',
            '<!-- ACTIVITY_START -->': '<!-- ACTIVITY_END -->',
            '<!-- STATS_START -->': '<!-- STATS_END -->'
        }
        
        sections = {
            '<!-- PROJECTS_START -->': new_projects_section,
            '<!-- ACTIVITY_START -->': new_activity_section,
            '<!-- STATS_START -->': new_stats_section
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
        
        print("🎉 README.md updated successfully!")

if __name__ == "__main__":
    updater = GitHubReadmeUpdater()
    updater.update_readme()