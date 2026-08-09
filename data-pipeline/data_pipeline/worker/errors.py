"""Stable ingestion errors used to decide whether an SQS message is acknowledged."""


class IngestionError(RuntimeError):
    """Base error for S3/SQS ingestion."""


class S3EventValidationError(IngestionError):
    """The SQS body is not an allowed S3 ObjectCreated event."""


class OpenViduEventValidationError(IngestionError):
    """The SQS body claims to be an OpenVidu egress event but is not valid."""


class UnsupportedMessageError(IngestionError):
    """The SQS body matches no known message contract."""


class MeetingContextUnresolvedError(IngestionError):
    """An OpenVidu room could not be mapped to a project/meeting pair."""


class S3MetadataError(IngestionError):
    """S3 object metadata could not be read or failed validation."""


class S3DownloadError(IngestionError):
    """The S3 object could not be downloaded or validated."""


class UploadAlreadyProcessing(IngestionError):
    """Another worker currently owns the same upload event."""


class PipelineProcessingError(IngestionError):
    """The existing meeting pipeline did not reach a durable success state."""


__all__ = [
    "IngestionError",
    "MeetingContextUnresolvedError",
    "OpenViduEventValidationError",
    "PipelineProcessingError",
    "S3DownloadError",
    "S3EventValidationError",
    "S3MetadataError",
    "UnsupportedMessageError",
    "UploadAlreadyProcessing",
]
