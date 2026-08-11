from apps.simulator.main import TransactionSimulator


def test_simulator_is_seeded_and_emits_valid_events() -> None:
    left = TransactionSimulator(seed=7)
    right = TransactionSimulator(seed=7)
    left_event, left_label = left.next()
    right_event, right_label = right.next()
    assert left_event.user_id == right_event.user_id
    assert left_event.amount == right_event.amount
    assert left_label == right_label
