"""Unit tests for Features/othello.py pure-logic helpers."""

from Features.othello import (
    apply_move,
    choose_ai_move,
    clone_board,
    coin_key,
    evaluate_board,
    get_flipped,
    get_valid_moves,
    minimax,
    new_board,
    opponent,
    othello_game_key,
    othello_index_key,
    player_line,
    player_name,
)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def empty_board():
    return [[0] * 8 for _ in range(8)]


# ---------------------------------------------------------------------------
# new_board
# ---------------------------------------------------------------------------

class TestNewBoard:
    def test_initial_layout(self):
        board = new_board()
        assert len(board) == 8
        assert all(len(row) == 8 for row in board)
        assert board[3][3] == 2
        assert board[4][4] == 2
        assert board[3][4] == 1
        assert board[4][3] == 1

    def test_empty_cells(self):
        board = new_board()
        stone_count = sum(cell != 0 for row in board for cell in row)
        assert stone_count == 4


# ---------------------------------------------------------------------------
# opponent
# ---------------------------------------------------------------------------

class TestOpponent:
    def test_black_to_white(self):
        assert opponent(1) == 2

    def test_white_to_black(self):
        assert opponent(2) == 1


# ---------------------------------------------------------------------------
# clone_board
# ---------------------------------------------------------------------------

class TestCloneBoard:
    def test_deep_copy(self):
        board = new_board()
        cloned = clone_board(board)
        cloned[0][0] = 99
        assert board[0][0] == 0

    def test_contents_match(self):
        board = new_board()
        cloned = clone_board(board)
        assert board == cloned


# ---------------------------------------------------------------------------
# get_flipped / get_valid_moves
# ---------------------------------------------------------------------------

class TestGetFlipped:
    def test_initial_board_flip(self):
        board = new_board()
        flipped = get_flipped(board, 2, 3, 1)
        assert (3, 3) in flipped

    def test_no_flip_on_empty(self):
        board = empty_board()
        assert get_flipped(board, 0, 0, 1) == []

    def test_no_flip_own_stone(self):
        board = new_board()
        flipped = get_flipped(board, 3, 4, 1)
        assert flipped == []


class TestGetValidMoves:
    def test_initial_moves_black(self):
        board = new_board()
        moves = get_valid_moves(board, 1)
        assert len(moves) == 4
        expected = {(2, 3), (3, 2), (4, 5), (5, 4)}
        assert set(moves) == expected

    def test_initial_moves_white(self):
        board = new_board()
        moves = get_valid_moves(board, 2)
        assert len(moves) == 4

    def test_empty_board_no_moves(self):
        board = empty_board()
        assert get_valid_moves(board, 1) == []


# ---------------------------------------------------------------------------
# apply_move
# ---------------------------------------------------------------------------

class TestApplyMove:
    def test_valid_move(self):
        board = new_board()
        result = apply_move(board, 2, 3, 1)
        assert result is True
        assert board[3][2] == 1
        assert board[3][3] == 1

    def test_invalid_move(self):
        board = new_board()
        result = apply_move(board, 0, 0, 1)
        assert result is False


# ---------------------------------------------------------------------------
# evaluate_board
# ---------------------------------------------------------------------------

class TestEvaluateBoard:
    def test_symmetry_on_initial(self):
        board = new_board()
        score_black = evaluate_board(board, 1)
        score_white = evaluate_board(board, 2)
        assert score_black == -score_white

    def test_corner_bonus(self):
        board = empty_board()
        board[0][0] = 1
        score = evaluate_board(board, 1)
        assert score > 0

    def test_corner_penalty(self):
        board = empty_board()
        board[0][0] = 2
        score = evaluate_board(board, 1)
        assert score < 0


# ---------------------------------------------------------------------------
# minimax
# ---------------------------------------------------------------------------

class TestMinimax:
    def test_returns_integer(self):
        board = new_board()
        result = minimax(board, 1, 1, 1, True)
        assert isinstance(result, int)

    def test_depth_zero(self):
        board = new_board()
        result = minimax(board, 1, 1, 0, True)
        assert result == evaluate_board(board, 1)


# ---------------------------------------------------------------------------
# choose_ai_move
# ---------------------------------------------------------------------------

class TestChooseAiMove:
    def test_returns_valid_move(self):
        board = new_board()
        valid = get_valid_moves(board, 1)
        move = choose_ai_move(board, 1, "master")
        assert move in valid

    def test_no_moves_returns_none(self):
        board = empty_board()
        assert choose_ai_move(board, 1, "easy") is None


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

class TestKeyHelpers:
    def test_coin_key(self):
        assert coin_key(123, 456) == "community_coin:123:456"

    def test_othello_index_key(self):
        assert othello_index_key(10) == "othello_games_index:10"

    def test_othello_game_key(self):
        assert othello_game_key(10, "abc") == "othello_game:10:abc"


# ---------------------------------------------------------------------------
# player_line / player_name
# ---------------------------------------------------------------------------

class TestPlayerHelpers:
    def test_player_line_ai_black(self):
        game = {"black_id": 0, "white_id": 42}
        line = player_line(game)
        assert "AI" in line
        assert "<@42>" in line

    def test_player_line_pending_white(self):
        game = {"black_id": 1, "white_id": None}
        line = player_line(game)
        assert "まだ参加していません" in line

    def test_player_name_draw(self):
        game = {"black_id": 1, "white_id": 2}
        assert player_name(game, None) == "引き分け"

    def test_player_name_ai(self):
        game = {"black_id": 0, "white_id": 2}
        assert player_name(game, 1) == "AI"

    def test_player_name_user(self):
        game = {"black_id": 1, "white_id": 2}
        assert player_name(game, 2) == "<@2>"
