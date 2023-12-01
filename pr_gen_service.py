from configparser import NoSectionError
import shutil
import os
import sys
import structlog
from git import Repo, GitCommandError, RemoteProgress
from github import Github
from dotenv import load_dotenv
from github.GithubException import GithubException, UnknownObjectException
from logconfig import configure_logging
# Get the absolute path of the current script
# current_script_path = os.path.abspath(__file__)
# project_root = os.path.abspath(os.path.join(current_script_path, '..', '..'))
# # Add the scripts folder to sys.path
# sys.path.append(project_root)
# from central_logging import logconfig
configure_logging()
logger = structlog.get_logger(__name__) 

# logconfig.configure_logging('manser-pr-gen-script.log')
# logger = structlog.get_logger(__name__)


class PullRequestAutomationService(RemoteProgress):
    """
    This class delivers the GitHub mirroring automation files across GitHub SAP Signavio org.
    The script makes use of externalised config and is capable of shipping any files over auto PR.
    It creates auto PRs with "files changed" as GitHub action files with relevant jira ticket, commit message etc. which are configurable.
    It has the capability to run this in batches for "N" repositories every run and capture the last run repository to continue further from second run.
    """

    GITHUB_REMOTE = "git@github.com:"
    ORIGIN = "origin"
    DEFAULT_BRANCHES = ["main", "master"]

    def __init__(self, load_env_value):
        logger.info("Loading environment variables...")
        load_dotenv()
        logger.info(f"xyz: {load_env_value}")
        if load_env_value:
            self.token = Github(os.getenv('GITHUB_ACCESS_TOKEN'))
            self.org_name = os.getenv("GITHUB_ORG")
            logger.info("Authenticating...")
            self.org = self.token.get_organization(self.org_name)
        else:
            self.token = self.create_access_token()
            self.tokens = Github(self.token)
            self.org_name = "signavio"
            self.org = self.tokens.get_organization(self.org_name)
        self.jira_ticket = os.getenv('JIRA_TICKET')
        self.branch_name = os.getenv('BRANCH_NAME_PREFIX') + os.getenv('JIRA_TICKET') + os.getenv('BRANCH_NAME_SUFFIX')
        self.repo_count = int(os.getenv('REPO_COUNT'))
        self.last_repo = os.getenv('LAST_REPO')
        self.git_commit_msg = os.getenv('GIT_COMMIT_MSG')
        self.git_pr_title = os.getenv('GIT_PR_TITLE')
        self.git_pr_test = os.getenv('GIT_PR_TEST')
        self.tmp_dir = os.getenv('TMP_DIR')
        self.file_to_sync = os.getenv('FILE_TO_SYNC_PATH')
        self.dir_to_sync = os.getenv('DIR_TO_SYNC')
        logger.info("Initialisation completed")

    def commit_and_push(self, repo_name):
        """Adds, commits and pushes files. It validates if no changes are there before commit and push.
            It copies the files from the FILE_TO_SYNC_PATH location in .env file to the cloned repostory.
            This is then added, committed and pushed.
        """
        logger.info("Staging files...")
        logger.info(f"Branch name: {self.branch_name}")

        if not self.dir_to_sync == '':
            repo_dir_path = os.path.join(self.repo_dir, self.dir_to_sync)
        else:
            repo_dir_path = self.repo_dir

        logger.info(f"New files to be send in PR will be copied under dir: {repo_dir_path}")
        curr_dir = os.getcwd()
        logger.info(f"Current dir: {curr_dir}")
        dir_name = os.path.join(curr_dir, self.file_to_sync)

        try:
            os.makedirs(repo_dir_path, exist_ok=True)
            shutil.copy(dir_name, repo_dir_path)
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
                self.validate_and_throw_err("already exists", "Branch " + self.branch_name + " already exists", e)
                repo.git.checkout(self.branch_name)
                logger.info(f"Branch {self.branch_name} already exist, checked out.")

            repo.git.add('--all')

            diff = repo.git.diff('HEAD', name_only=True)
            logger.info(diff)

            if not diff == '':
                self.add_git_config(repo)
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
        logger.info(f"Cloning repository {repo_name}")
        try:
            Repo.clone_from(self.repo_git_link, self.repo_dir)
        except GitCommandError as e:
            self.validate_and_throw_err("already exists and is not an empty directory", "Repository not empty, not proceeding with cloning.", e)

        logger.info(f"Cloning completed for repository {repo_name} to {self.repo_dir}")

    def set_gitlink_n_repopath(self, repo_name, git_link):
        """Set the repository path to temp directory and coins git repo link.
        :param repo_name: string
        """
        self.repo_git_link = git_link
        logger.info(f"Current git repo link: {self.repo_git_link}")
        self.repo_dir = self.get_clone_dir() + repo_name
        logger.info(f"Repo directory: {self.repo_dir}")

    def get_clone_dir(self):
        """Creates a temp directory for cloning if not already present.
        :param repo_name: string
        :rtype: tmp_dir: string
        """
        isExist = os.path.exists(self.tmp_dir)
        if not isExist:
            os.makedirs(self.tmp_dir)
            logger.info(f"A new clone directory is created at {self.tmp_dir}")
        else:
            logger.info(f"Clone directory already exists at {self.tmp_dir}")
        return self.tmp_dir


    def file_exists(self, repo) -> bool:
        """Checks if file_to_sync to sync exists in the repository
        :param repo: class:`github.Repository.Repository`
        :rtype: boolean
        """
        try:
            repo.get_contents(self.file_to_sync)
            return True
        except UnknownObjectException:
            logger.info(f'Automation file:{self.file_to_sync} already exists in repo: {repo.name}')
            return False

    def create_pr(self, repo):
        """Creates PR for the files newly added and the branch pushed.
        It validates if any open PR with the same jira ticket is already available in the repository.
        If not present if proceeds with PR creation.
        :param repo: class:`github.Repository.Repository`
        """
        pull_requests = repo.get_pulls(state='open', sort='created', base=self.base_branch_name)
        pr_exists = False

        for pr in pull_requests:
            if pr.body is not None and self.jira_ticket in pr.body:
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

            pull_request = repo.create_pull(self.git_pr_title, pr_body, self.base_branch_name, self.branch_name)

            logger.info(f'PR successfuly created, PR number: {pull_request.number}🎉🎉 ')
            logger.info(f"PR title: {self.git_pr_title} ")
            logger.info(f"PR body:  {pr_body}")


    def add_git_config(self, repo):
        config_reader = repo.config_reader()
        try:
            user_name = config_reader.get_value("user", "name")
            user_email = config_reader.get_value("user", "email")
            logger.info(f"Config user.name: {user_name}, Config user.email: {user_email}")
        except NoSectionError as e:
            logger.warn(f"NoSectionError - {e}")
            logger.info("No git Configuration is present so moving ahead with configuration")
            config_writer = repo.config_writer()
            config_writer.set_value("user", "name", "GitHubApps")
            config_writer.set_value("user", "email", "prateek.kesarwani@sap.com")
            logger.info("Configuration is Completed")


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

            filter_condition1 = (is_first_run and firstrun_counter <= self.repo_count) or (found_last_repo and continue_counter <= self.repo_count)
            filter_condition2 = self.base_branch_name in self.DEFAULT_BRANCHES and repo.visibility == 'private'
            all_filters = filter_condition1 and filter_condition2
            if all_filters and not self.file_exists(repo):
                try:
                    repo_git_link = self.GITHUB_REMOTE + self.org_name + "/" + repo.name + ".git"
                    self.set_gitlink_n_repopath(repo.name, repo_git_link)
                    self.clone_repository(repo.name)
                    self.commit_and_push(repo.name)
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

    pr_service = PullRequestAutomationService(True)
    pr_service.create_prs_in_batches()

    logger.info('Successfuly completed PR generation for this run..🎉🎉🎉 ')
