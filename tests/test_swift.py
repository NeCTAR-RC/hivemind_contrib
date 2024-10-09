from hivemind_contrib import swift


def test_size_to_bytes():
    assert swift.size_to_bytes("1234567B") == 1234567
    assert swift.size_to_bytes("123456MB") == 134044080384
    assert swift.size_to_bytes("12345GB") == 13966714356360
    assert swift.size_to_bytes("1234TB") == 1454742194200864
    assert swift.size_to_bytes("123PB") == 151092778008061536
    assert swift.size_to_bytes("12ZB") == 16004985270355602494976
