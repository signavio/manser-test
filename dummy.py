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
  
    # configure_logging()
    # logger = structlog.get_logger(__name__) 
    
    def __init__(self, app_id, private_key_path, installation_id ):
        super().__init__()

        self.app_id_value = app_id
        self.private_key_path_value = private_key_path
        self.installation_id_value = installation_id
            
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
                creation_date = repo.created_at.replace(tzinfo=None)

                if creation_date >= cutoff_date:
                    repocount_tracker += 1
                    repo_within_30_days.extend(repo.name)
                    try:
                        self.set_gitlink_n_repopath(repo.name)
                        self.clone_repository(repo.name)
                        self.commit_and_push()
                        self.create_pr(repo)
                
                    except GithubException as e:
                        raise e
        
    # Check if all PRs are done for all repositories in the organization
        self.check_if_all_prs_done(repocount_tracker, total_repos)

            
if __name__ == "__main__":
    logger.info("Starting pull request creation for Managed Services GitHub mirror automation...")
    
    pr_service = PullRequestForNewRepos(app_id = sys.argv[1], private_key_path = sys.argv[2], installation_id= sys.argv[3])
    # pr_service.base_branch_name = "main"
    pr_service.create_prs_in_batches()

    logger.info('Successfuly completed PR generation for this run..🎉🎉🎉 ')
