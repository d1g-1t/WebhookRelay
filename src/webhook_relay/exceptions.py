import uuid


class WebhookRelayError(Exception):
    pass


class EndpointNotFoundError(WebhookRelayError):
    def __init__(self, endpoint_id: uuid.UUID):
        self.endpoint_id = endpoint_id
        super().__init__(f"Endpoint {endpoint_id} not found")


class EventNotFoundError(WebhookRelayError):
    def __init__(self, event_id: uuid.UUID):
        self.event_id = event_id
        super().__init__(f"Event {event_id} not found")


class DeadLetterNotFoundError(WebhookRelayError):
    def __init__(self, dlq_id: uuid.UUID):
        self.dlq_id = dlq_id
        super().__init__(f"Dead letter entry {dlq_id} not found")


class DuplicateEventError(WebhookRelayError):
    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(f"Event with idempotency key '{idempotency_key}' already exists")


class RecentlyReplayedError(WebhookRelayError):
    pass


class EndpointInactiveError(WebhookRelayError):
    def __init__(self, endpoint_id: uuid.UUID):
        self.endpoint_id = endpoint_id
        super().__init__(f"Endpoint {endpoint_id} is inactive")


class EventTypeFilterError(WebhookRelayError):
    def __init__(self, event_type: str, endpoint_id: uuid.UUID):
        super().__init__(
            f"Event type '{event_type}' not accepted by endpoint {endpoint_id}"
        )
