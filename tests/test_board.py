import pytest
from board import Board
from tests.board_adapter import BoardAdapter

def test_validate_move_and_win_line():
    b = Board(size=15, win_len=5)
    A = BoardAdapter(b)

    # X tạo hàng ngang 5 quân tại y=7
    y_line = 7
    for i in range(5):
        ok = A.place(i, y_line, "X")
        if not ok:
            # Nếu board ép phải luân phiên, ta nhường lượt bằng 1 nước O ở nơi vô hại
            assert A.place(i, 0, "O") is True
            assert A.place(i, y_line, "X") is True

    assert A.check_win(4, y_line, "X") is True

def test_reject_occupied_and_bounds():
    b = Board(size=15, win_len=5)
    A = BoardAdapter(b)

    assert A.place(3, 3, "X") is True
    # cùng 1 ô, quân khác -> phải bị từ chối
    assert A.place(3, 3, "O") is False
    # biên ngoài bàn -> phải từ chối
    assert A.place(99, 0, "X") is False
