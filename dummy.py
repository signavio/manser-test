import structlog
from logconfig import configure_logging
from github.GithubException import GithubException
from datetime import datetime, timedelta

from pr_gen_service import PullRequestAutomationService  

configure_logging()
logger = structlog.get_logger(__name__) 

GITHUB_REMOTE = "git@github.com:"
ORIGIN = "origin"

obj=PullRequestAutomationService()

class PullRequestForNewRepos(PullRequestAutomationService):
  
    # configure_logging()
    # logger = structlog.get_logger(__name__) 
    
    def __init__(self):
        super().__init__()

            
    def create_prs_in_batches(self):  
        """Creates PRs for repositories created within the last 30 days.
        It pushes the files to be delivered as per the configuration env var files.
        """
        cutoff_date = datetime.now() - timedelta(days=60)
        repocount_tracker = 0

        logger.info(f"Filtering repositories in org: {obj.org_name} by creation time asc and creating PRs.")
        print(type(self.org))

        for repo in obj.org.get_repos(direction="desc", sort="created", type="all"):
            repocount_tracker += 1
            if repo == "manser-test":
                creation_date = repo.created_at.replace(tzinfo=None)

                if creation_date >= cutoff_date:
                    try:
                        obj.set_gitlink_n_repopath(repo.name)
                        obj.clone_repository(repo.name)
                        obj.commit_and_push()
                        obj.create_pr(repo)
                
                    except GithubException as e:
                        raise e
                
    # Check if all PRs are done for all repositories in the organization
        obj.check_if_all_prs_done(repocount_tracker)

            
if __name__ == "__main__":
    logger.info("Starting pull request creation for Managed Services GitHub mirror automation...")

    pr_service = PullRequestForNewRepos()
    pr_service.base_branch_name = "main"
    pr_service.create_prs_in_batches()

    logger.info('Successfuly completed PR generation for this run..🎉🎉🎉 ')
