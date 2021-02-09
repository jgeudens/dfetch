"""Version Control system."""

import os
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import dfetch.manifest.manifest
from dfetch.log import get_logger
from dfetch.project.metadata import Metadata
from dfetch.project.version import Version
from dfetch.util.util import hash_directory, safe_rm

logger = get_logger(__name__)


class VCS(ABC):
    """Abstract Version Control System object.

    This object represents one Project entry in the Manifest.
    It can be updated.
    """

    NAME = ""
    DEFAULT_BRANCH = ""

    def __init__(self, project: dfetch.manifest.project.ProjectEntry) -> None:
        """Create the VCS."""
        self._project = project
        self.__metadata = Metadata.from_project_entry(self._project)

    def check_wanted_with_local(self) -> Tuple[Optional[Version], Optional[Version]]:
        """Given the project entry in the manifest, get the relevant version from disk.

        Returns:
            Tuple[Optional[Version], Optional[Version]]: Wanted, Have
        """
        if not os.path.exists(self.__metadata.path):
            return (self.wanted_version, None)

        on_disk = Metadata.from_file(self.__metadata.path).version

        if self.wanted_version.tag:
            return (Version(tag=self.wanted_version.tag), Version(tag=on_disk.tag))

        wanted_branch, on_disk_branch = "", ""
        if not (self.wanted_version.revision and self.revision_is_enough()):
            wanted_branch = self.wanted_version.branch or self.DEFAULT_BRANCH
            on_disk_branch = on_disk.branch

        wanted_revision = (
            self.wanted_version.revision
            or self._latest_revision_on_branch(wanted_branch)
        )

        return (
            Version(
                revision=wanted_revision,
                branch=wanted_branch,
            ),
            Version(revision=on_disk.revision, branch=on_disk_branch),
        )

    def update_is_required(self) -> Optional[Version]:
        """Check if this project should be upgraded."""
        wanted, current = self.check_wanted_with_local()

        if wanted == current:
            logger.print_info_line(self._project.name, f"up-to-date ({current})")
            return None

        logger.debug(self._project.name, f"Current ({current}), Available ({wanted})")
        return wanted

    def update(self) -> None:
        """Update this VCS if required."""
        to_fetch = self.update_is_required()

        if not to_fetch:
            return

        if os.path.exists(self.local_path):
            logger.debug(f"Clearing destination {self.local_path}")
            safe_rm(self.local_path)

        actually_fetched = self._fetch_impl(to_fetch)
        logger.print_info_line(self._project.name, f"Fetched {actually_fetched}")
        self.__metadata.fetched(actually_fetched)

        logger.debug(f"Writing repo metadata to: {self.__metadata.path}")
        self.__metadata.dump()

        logger.info(
            hash_directory(self.local_path, skiplist=[self.__metadata.FILENAME])
        )

    def check_for_update(self) -> None:
        """Check if there is an update available."""
        on_disk_version = None
        if os.path.exists(self.__metadata.path):
            on_disk_version = Metadata.from_file(self.__metadata.path).version

        latest_version = self._check_for_newer_version()

        if not on_disk_version:
            self._log_project(f"available ({latest_version})")
        elif latest_version == on_disk_version:
            self._log_project(f"up-to-date ({latest_version})")
        elif on_disk_version == self.wanted_version:
            self._log_project(
                f"wanted & current ({on_disk_version}), available ({latest_version})"
            )
        else:
            self._log_project(
                f"wanted ({self.wanted_version}), current ({on_disk_version}), available ({latest_version})"
            )

    def _log_project(self, msg: str) -> None:
        logger.print_info_line(self._project.name, msg)

    @staticmethod
    def _log_tool(name: str, msg: str) -> None:
        logger.print_info_line(name, msg.strip())

    @property
    def local_path(self) -> str:
        """Get the local destination of this project."""
        return self._project.destination

    @property
    def wanted_version(self) -> Version:
        """Get the wanted version of this VCS."""
        return self.__metadata.version

    @property
    def remote(self) -> str:
        """Get the remote URL of this VCS."""
        return self.__metadata.remote_url

    @abstractmethod
    def check(self) -> bool:
        """Check if it can handle the type."""

    @staticmethod
    @abstractmethod
    def revision_is_enough() -> bool:
        """See if this VCS can uniquely distinguish branch with revision only."""

    @abstractmethod
    def _latest_revision_on_branch(self, branch: str) -> str:
        """Get the latest revision on a branch."""

    @staticmethod
    @abstractmethod
    def list_tool_info() -> None:
        """Print out version information."""

    def _check_for_newer_version(self) -> Version:
        """Check if a newer version is available on the given branch."""
        if self.wanted_version.tag:
            # We could interpret tags here
            return Version(tag=self.wanted_version.tag)

        branch = self.wanted_version.branch or self.DEFAULT_BRANCH
        return Version(revision=self._latest_revision_on_branch(branch), branch=branch)

    @abstractmethod
    def _fetch_impl(self, version: Version) -> Version:
        """Fetch the given version of the VCS, should be implemented by the child class."""
