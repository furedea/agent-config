from shop.sync import sync_orders


def test_sync_skips_unpaid_orders(mocker):
    client = mocker.Mock()
    client.list_orders.return_value = [mocker.Mock(paid=False, id=1)]
    store = mocker.Mock()
    sync_orders(client, store)
    store.save.assert_not_called()


def test_sync_retries_after_a_timeout(mocker):
    client = mocker.Mock()
    client.list_orders.side_effect = [TimeoutError(), [mocker.Mock(paid=True, id=2)]]
    store = mocker.Mock()
    sync_orders(client, store)
    store.save.assert_called_once()
