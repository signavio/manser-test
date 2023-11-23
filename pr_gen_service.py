import base64
import secrets
import shutil
import os
import subprocess
import sys
import requests
import structlog
from logconfig import configure_logging
from git import Repo, GitCommandError, RemoteProgress
from github import Github ,GithubApp, GithubIntegration
from dotenv import load_dotenv
from github.GithubException import GithubException
import jwt
import time

configure_logging()
logger = structlog.get_logger(__name__)


class PullRequestAutomationService(RemoteProgress):
    """
    This class delivers the GitHub mirroring automation files across GitHub Signavio org.
    The script makes use of externalised config and is capable of shipping any files over auto PR.
    It creates auto PRs with "files changed" as GitHub action files with relevant jira ticket, commit message etc. which are configurable.
    It has the capability to run this in batches for "N" reposiotories every run and capture the last run repository to continue further from second run.
    """

    GITHUB_REMOTE = "git@github.com:"
    ORIGIN = "origin"

    def __init__(self):
        logger.info("Loading environment variables...")
        load_dotenv()
        self.org_name = os.getenv("GITHUB_ORG")
        logger.info("Authenticating...")
        self.jira_ticket = os.getenv('JIRA_TICKET')
        self.branch_name = os.getenv('BRANCH_NAME_PREFIX') + os.getenv('JIRA_TICKET') + os.getenv('BRANCH_NAME_SUFFIX')
        self.repo_count = int(os.getenv('REPO_COUNT'))
        self.last_repo = os.getenv('LAST_REPO')
        self.git_commit_msg = os.getenv('GIT_COMMIT_MSG')
        self.git_pr_title = os.getenv('GIT_PR_TITLE')
        self.git_pr_test = os.getenv('GIT_PR_TEST')
        self.app_id = sys.argv[1]
        self.private_key_path = sys.argv[2]
        self.installation_id = sys.argv[3]
        self.org, self.token = self.authenticate_github()
        logger.info("Initialisation completed")

    def authenticate_github(self):
        try:
            token = self.create_access_token()
            self.github_instance = Github(token)
            org = self.github_instance.get_organization(self.org_name)
            return org ,token
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
            'iss': self.app_id
        }
        
        encoded_jwt = jwt.encode(payload, self.private_key_path, algorithm='RS256')
        
        response = requests.post(
        f"https://api.github.com/app/installations/{self.installation_id}/access_tokens",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {encoded_jwt}",
        },
        timeout=60,
        )

        return response.json()["token"]

    def commit_and_push(self):
        """Adds, commits and pushes files. It validates if no changes are there before commit and push.
            It copies the files from the FILE_TO_SYNC_PATH location in .env file to the cloned repostory.
            This is then added, committed and pushed.
        """
        logger.info("Staging files...")
        file_to_sync = os.getenv('FILE_TO_SYNC_PATH')
        logger.info(f"Branch name: {self.branch_name}")

        dir_to_sync = os.getenv('DIR_TO_SYNC')
        # dir_to_sync = os.getcwd() + ".github"
        print(dir_to_sync)
        if not dir_to_sync == '':
            repo_dir_path = os.path.join(self.repo_dir, dir_to_sync)
            print(f'a = {repo_dir_path}')
        else:
            repo_dir_path = self.repo_dir
            print(f'b = {repo_dir_path}')

        logger.info(f"New files to be send in PR will be copied under dir: {repo_dir_path}")
        curr_dir = self.repo_dir
        logger.info(f"Current dir: {curr_dir}")
        dir_name = os.path.join(curr_dir, file_to_sync)
        print(dir_name)

        try:
            os.makedirs(repo_dir_path, exist_ok=True)
            shutil.copytree(dir_name, repo_dir_path, dirs_exist_ok=True)
            logger.info('GitHub action locally copied successfully to temp repo.')
            self.remove_mac_metadatafile(repo_dir_path)
        except Exception as e:
            logger.error('Directory not copied.')
            raise e

        try:
            repo = Repo.init(self.repo_dir)
            try:
                repo.git.checkout('-b', self.branch_name)
                logger.info(f"Created and checked out to branch: {self.branch_name}")
            except GitCommandError as e:
                self.validate_and_throw_err("already exists", "Branch "+self.branch_name+" already exists", e)
                repo.git.checkout(self.branch_name)
                logger.info(f"Branch {self.branch_name} already exist, checked out.")

            repo.git.add('--all')

            diff = repo.git.diff('HEAD', name_only=True)
            logger.info(diff)

            if not diff == '':
                repo.git.pull
                repo.git.commit('-m', self.git_commit_msg, None)
                repo.git.push('-u', self.ORIGIN, self.branch_name)
            else:
                logger.info("No changes to commit!")
        except GitCommandError as e:
            logger.error("Unexpected error")
            raise e

    def remove_mac_metadatafile(self, repo_dir_path):
        """Utility fuction to remove mac metadata file.
        :param repo_dir_path: string
        """
        metadata_path = repo_dir_path + "/.DS_Store"
        isExist = os.path.exists(metadata_path)
        if isExist:
            os.remove(metadata_path)

    def validate_and_throw_err(self, str_to_match, info_msg, error):
        """Validates for string matches and throws error if the string doesn't match.

        :param str_to_match: string
            String in the error that needs to be matched.
        :param info_msg: string
            If the string matches, the info message to be logged.
        :param error: GitCommandError object
        """
        if str_to_match in error.stderr:
            logger.warn(info_msg)
        else:
            raise error

    def clone_repository(self, repo_name):
        """Clones current repository to the temp directory. Will not proceed with clone if already exisits error is thrown.
        :param repo_name: string
        """
        # self.repo_git_links = repo_clone_url
        logger.info(f"Cloning repository {repo_name}")
        try:
            print(os.getcwd())
            os.chdir(self.repo_dir)
            print(os.getcwd())
            Repo.clone_from(self.repo_git_link, self.repo_dir)
            os.chdir("..")
            print(os.getcwd())
        except GitCommandError as e:
            self.validate_and_throw_err("already exists and is not an empty directory", "Repository not empty, not proceeding with cloning.", e)

        logger.info(f"Cloning completed for repository {repo_name} to {self.repo_dir}")

    def set_gitlink_n_repopath(self, repo_name):
        """Set the repository path to temp directory and coins git repo link.
        :param repo_name: string
        """
        self.repo_git_link = f"https://x-access-token:{self.token}@github.com/{self.org_name}/{repo_name}.git"
        logger.info(f"Current git repo link: {self.repo_git_link}")
        curr_dirr = os.getcwd()
        logger.info(f"Current dir: {curr_dirr}")
        
        # # tmp_dir = os.path.join(curr_dirr, "tmp")
        self.repo_dir = os.path.join(curr_dirr, "tmp")
        os.makedirs(self.repo_dir, exist_ok=True)
        # #+ self.get_clone_dir() + repo_name
        os.chmod(self.repo_dir, 0o777)
        
        logger.info(f"Repo directory: {self.repo_dir}")

    def get_clone_dir(self):
        """Creates a temp directory for cloning if not already present.
        :param repo_name: string
        :rtype: tmp_dir: string
        """
        tmp_dir = os.getenv('TMP_DIR')
        isExist = os.path.exists(tmp_dir)
        if not isExist:
            os.makedirs(tmp_dir)
            logger.info(f"A new clone directory is created at {tmp_dir}")
        else:
            logger.info(f"Clone directory already exisits at {tmp_dir}")
        return tmp_dir

    def create_pr(self, repo):
        """Creates PR for the files newly added and the branch pushed.
        It validates if any open PR with the same jira ticket is already available in the repository.
        If not present if proceeds with PR creation.
        :param repo: class:`github.Repository.Repository`
        """
        repo_name = repo.name
        self.auth = self.github_instance.get_repo(repo_name)
        self.base_branch_name = repo.default_branch
        pull_requests = self.auth.get_pulls(state='open', sort='created', base=self.base_branch_name)
        print(pull_requests)
        pr_exists = False

        for pr in pull_requests:
            if self.jira_ticket in pr.body:
                pr_exists = True
                logger.info(f"PR number: {pr.number} already exists for the jira ticket: {self.jira_ticket} in repository: {repo.name}")

        if not pr_exists:
            logger.info(f"Creating PR in repository: {repo.name}")
            pr_body = """
            Jira ticket: %s
            ### Changes made
            1. %s
            ### Test
            2. %s
            """ % (self.jira_ticket, self.git_pr_title, self.git_pr_test)

            pull_request = self.auth.create_pull(title = self.git_pr_title, body = pr_body, base = self.base_branch_name, head = self.branch_name)

            logger.info(f'PR successfuly created, PR number: {pull_request.number}🎉🎉 ')
            logger.info(f"PR title: {self.git_pr_title} ")
            logger.info(f"PR body:  {pr_body}")

    def create_prs_in_batches(self):
        """Creates PRs for repositories in the given org in batches based on the confiuration(REPO_COUNT).
        It pushes the files to be delivered as per the configuration env var files.
        For the first run it creates PR for the given count(REPO_COUTN of repos.
        From second run onwards, the configuration can be updated to provide that last repo name(LST_REPO) which was covered. This will be available in the log.
        """
        firstrun_counter = 1
        continue_counter = 1
        repocount_tracker = 0
        is_first_run = False
        found_last_repo = False

        total_repos = self.org.get_repos().totalCount
        logger.info(f"Total repos in organisation {self.org_name}: {total_repos} ")

        if self.repo_count > total_repos:
            logger.info(f"Repo count: {self.repo_count} given is greater than total no: of repositories:{total_repos} in the org {self.org_name}: {total_repos}")
            self.repo_count = total_repos

        if self.last_repo == '':
            is_first_run = True
            logger.info("Identified first time run, as last repo is found empty")

        logger.info(f"Filtering repositories in org: {self.org_name} by creation time asc and creating PRs for {self.repo_count} repositories.")
        for repo in self.org.get_repos(direction="asc", sort="created", type="all"):
            repocount_tracker = repocount_tracker + 1
            self.base_branch_name = repo.default_branch
            logger.info(f"Retrieved repository:  {repo.name}...")

            if repo.name == self.last_repo:
                found_last_repo = True
                logger.info(f"Identified a continuation run, found last repo till PR created as:  {repo.name}...")
                # continue

            if not is_first_run and not found_last_repo:
                continue

            filter_condition = (is_first_run and firstrun_counter <= self.repo_count) or (found_last_repo and continue_counter <= self.repo_count)

            if filter_condition:
                try:
                    self.set_gitlink_n_repopath(repo.name)
                    self.clone_repository(repo.name)
                    self.commit_and_push()
                    self.create_pr(repo)

                except GithubException as e:
                    raise e
            else:
                repos_completed = self.get_repos_completed(found_last_repo, firstrun_counter, continue_counter)
                logger.info(f"Completed applying PRs for {repos_completed}/{total_repos} repositories in {self.org_name}")
                logger.info(f"Last repository in this run is {repo.name}")
                break

            if found_last_repo:
                continue_counter = continue_counter + 1
            else:
                firstrun_counter = firstrun_counter + 1

        self.check_if_all_prs_done(repocount_tracker, total_repos)

    def get_repos_completed(self, found_last_repo, firstrun_counter, continue_counter):
        """Utility method to find number of repos where PR generation is completed.
        """
        if found_last_repo:
            repos_complete = continue_counter - 1
        else:
            repos_complete = firstrun_counter - 1
        return repos_complete

    def check_if_all_prs_done(self, repocount_tracker, total_repos):
        """Utility method if PR generation is completed for all repositories in an org.
        """
        if repocount_tracker == total_repos:
            logger.info(f"Completed creating PRs for all {total_repos} repositories in the org: {self.org_name} 🎉🎉🎉.")


if __name__ == "__main__":
    logger.info("Starting pull request creation for Managed Services GitHub mirror automation...")

    # access_token = PullRequestAutomationService.create_access_token()
    pr_service = PullRequestAutomationService()
    pr_service.create_prs_in_batches()

    logger.info('Successfuly completed PR generation for this run..🎉🎉🎉 ')
