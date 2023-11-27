import time
from github import Github
import jwt
import requests
import structlog
from logconfig import configure_logging
from github.GithubException import GithubException
from datetime import datetime, timedelta
import sys


from pr_gen_service import PullRequestAutomationService  

configure_logging()
logger = structlog.get_logger(__name__) 

GITHUB_REMOTE = "git@github.com:"
ORIGIN = "origin"


class PullRequestForNewRepos(PullRequestAutomationService):
    
    # def authenticate_github(self):
    #     try:
    #         token = self.create_access_token()
    #         self.github_instance = Github(token)
    #         self.org = self.github_instance.get_organization(self.org_name)
    #         return token, self.org
    #     except GithubException as e:
    #         logger.error(f"GitHub authentication error: {e}")
    #         raise
    
    def __init__(self):
        # super().__init__(token=self.authenticate_github())
        logger.info("Start")
        self.org_name = "signavio"
        self.app_id_value = sys.argv[1]
        self.private_key_path_value = sys.argv[2]
        self.installation_id_value = sys.argv[3]
        super().__init__(tokens=self.authenticate_github())
        self.org, self.token = self.authenticate_github()
        self.git_commit_msg = "Added GitHub action for mirroring automation required for SAP compliance."
        self.git_pr_title = "CloudOS Managed Services: applying git-mirror automation required for SAP compliance."
        self.git_pr_test = "No action needed."
        self.branch_name = "parvathy/" + "SIGMANSER-1234" + "_gitMirror"
        self.tmp_dir = "/tmp/repo_clone/"
        self.file_to_sync = "<path to GH action>/.github/workflows/git_mirror.yaml"
        self.dir_to_sync = ".github"
        logger.info("Done")
        # super().__init__(self.org, self.token, self.git_commit_msg, self.git_pr_title, self.git_pr_test, self.branch_name, self.tmp_dir, self.file_to_sync, self.dir_to_sync, self.org_name)
        
        
    def authenticate_github(self):
        try:
            token = self.create_access_token()
            self.github_instance = Github(token)
            self.org = self.github_instance.get_organization(self.org_name)
            return token, self.org
        except GithubException as e:
            logger.error(f"GitHub authentication error: {e}")
            raise
        
    def create_access_token(self):
        payload = {
            # Issued at time
            'iat': int(time.time()),
            # JWT expiration time (10 minutes maximum)
            'exp': int(time.time()) + 600,
            # GitHub App's identifier
            'iss': self.app_id_value
        }
        
        encoded_jwt = jwt.encode(payload, self.private_key_path_value, algorithm='RS256')
        
        response = requests.post(
        f"https://api.github.com/app/installations/{self.installation_id_value}/access_tokens",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {encoded_jwt}",
        },
        timeout=60,
        )

        return response.json()["token"]
    
            
    def create_prs_in_batches(self):  
        """Creates PRs for repositories created within the last 30 days.
        It pushes the files to be delivered as per the configuration env var files.
        """
        cutoff_date = datetime.now() - timedelta(days=60)
        repocount_tracker = 0
        repo_within_30_days= []
        total_repos= len(repo_within_30_days)

        logger.info(f"Filtering repositories in org: {self.org} by creation time asc and creating PRs.")
        print(type(self.org))

        for repo in self.org.get_repos(direction="desc", sort="created", type="all"):
            if repo.name == "Manser-repo-trigger-prgen":
                git_link = f"https://x-access-token:{self.token}@github.com/{self.org_name}/{repo.name}.git"
                creation_date = repo.created_at.replace(tzinfo=None)

                if creation_date >= cutoff_date:
                    repocount_tracker += 1
                    repo_within_30_days.extend(repo.name)
                    try:
                        self.set_gitlink_n_repopath(repo.name, git_link)
                        self.clone_repository(repo.name)
                        self.commit_and_push(repo.name, repo)
                        self.create_pr(repo) 
                
                    except GithubException as e:
                        raise e
        
    # Check if all PRs are done for all repositories in the organization
        self.check_if_all_prs_done(repocount_tracker, total_repos)

            
if __name__ == "__main__":
    logger.info("Starting pull request creation for Managed Services GitHub mirror automation...")
    
    pr_service = PullRequestForNewRepos()
    # pr_service.base_branch_name = "main"
    pr_service.create_prs_in_batches()

    logger.info('Successfuly completed PR generation for this run..🎉🎉🎉 ')
