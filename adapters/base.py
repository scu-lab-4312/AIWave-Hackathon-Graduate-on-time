"""Transport-independent specialist client interface."""

from abc import ABC, abstractmethod

from shared.contracts import HandoffRequest, SpecialistResponse


class SpecialistClient(ABC):
    @abstractmethod
    def invoke(self, request: HandoffRequest) -> SpecialistResponse:
        """Invoke a specialist and return a contract-validated response."""
