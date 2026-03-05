from db.repositories import BacktestRepository


def test_save_preserves_existing_live_flag_when_not_provided():
    repo = BacktestRepository()
    run_id = "tmp_live_flag_preserve"

    repo.save(run_id, {"total_pnl": 10.0}, is_live=True)
    first = repo.get_by_id(run_id)
    assert first is not None
    assert first.get("is_live") is True

    # Simulate partial update path that does not pass is_live.
    repo.save(run_id, {"total_pnl": 20.0})
    second = repo.get_by_id(run_id)
    assert second is not None
    assert second.get("is_live") is True

    repo.delete(run_id)
