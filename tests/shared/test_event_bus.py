"""Pruebas unitarias del bus de eventos en memoria (T32)."""
import uuid
from dataclasses import dataclass

from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.events import TicketRegistered
from app.helpdesk.domain.ticket import Ticket
from app.shared.domain.aggregate_root import DomainEvent
from app.shared.infrastructure.event_bus import InMemoryEventBus


@dataclass(frozen=True, kw_only=True)
class OtherEvent(DomainEvent):
    value: int = 0


def _ticket_registered() -> TicketRegistered:
    return TicketRegistered(ticket_id=uuid.uuid4(), workspace_id=uuid.uuid4(), reporter_id=uuid.uuid4(), has_evidence=False)


def test_handler_receives_published_event():
    bus, received = InMemoryEventBus(), []
    bus.subscribe(TicketRegistered, received.append)
    event = _ticket_registered()
    bus.publish(event)
    assert received == [event]


def test_handler_only_receives_its_event_type():
    bus, received = InMemoryEventBus(), []
    bus.subscribe(TicketRegistered, received.append)
    bus.publish(OtherEvent(value=1))
    assert received == []


def test_handler_on_base_class_receives_all_events():
    bus, received = InMemoryEventBus(), []
    bus.subscribe(DomainEvent, received.append)
    bus.publish_all([_ticket_registered(), OtherEvent()])
    assert len(received) == 2


def test_handlers_run_in_subscription_order_without_duplicates():
    bus, calls = InMemoryEventBus(), []
    first = lambda e: calls.append("first")  # noqa: E731
    second = lambda e: calls.append("second")  # noqa: E731
    bus.subscribe(TicketRegistered, first)
    bus.subscribe(TicketRegistered, second)
    bus.subscribe(TicketRegistered, first)
    bus.publish(_ticket_registered())
    assert calls == ["first", "second"]


def test_failing_handler_does_not_stop_the_others(caplog):
    bus, received = InMemoryEventBus(), []

    def broken(event):
        raise RuntimeError("falla simulada")

    bus.subscribe(TicketRegistered, broken)
    bus.subscribe(TicketRegistered, received.append)
    bus.publish(_ticket_registered())
    assert len(received) == 1
    assert "falla simulada" in caplog.text


def test_unsubscribe_stops_delivery():
    bus, received = InMemoryEventBus(), []
    bus.subscribe(TicketRegistered, received.append)
    bus.unsubscribe(TicketRegistered, received.append)
    bus.publish(_ticket_registered())
    assert received == []


def test_events_pulled_from_aggregate_are_delivered():
    bus, received = InMemoryEventBus(), []
    bus.subscribe(TicketRegistered, received.append)
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(), reporter_id=uuid.uuid4(), title="Error", description="Detalle", impact_level=ImpactLevel.LOW
    )
    bus.publish_all(ticket.pull_events())
    assert len(received) == 1 and received[0].ticket_id == ticket.id
