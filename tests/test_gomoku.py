"""Unit tests for Features/gomoku.py pure-logic helpers."""

from Features.gomoku import (
    AI_PLAYER_ID,
    BOARD_SIZE,
    candidate_moves,
    check_winner,
    coin_key,
    color_name,
    game_status_text,
    gomoku_game_key,
    gomoku_index_key,
    is_full,
    is_turn_user,
    longest_line_score,
    move_score,
    new_board,
    opponent,
    player_name,
    resolve_first_choice,
)


# ---------------------------------------------------------------------------
# new_board
# ---------------------------------------------------------------------------

class TestNewBoard:
    def test_dimensions(self):
        board = new_board()
        assert len(board) == BOARD_SIZE
        assert all(len(row) == BOARD_SIZE for row in board)

    def test_all_empty(self):
        board = new_board()
        assert all(cell == 0 for row in board for cell in row)


# ---------------------------------------------------------------------------
# opponent / color_name
# ---------------------------------------------------------------------------

class TestBasicHelpers:
    def test_opponent(self):
        assert opponent(1) == 2
        assert opponent(2) == 1

    def test_color_name(self):
        assert color_name(1) == "黒"
        assert color_name(2) == "白"


# ---------------------------------------------------------------------------
# is_full
# ---------------------------------------------------------------------------

class TestIsFull:
    def test_empty_not_full(self):
        assert is_full(new_board()) is False

    def test_full(self):
        board = [[1] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        assert is_full(board) is True


# ---------------------------------------------------------------------------
# check_winner
# ---------------------------------------------------------------------------

class TestCheckWinner:
    def test_no_winner_empty(self):
        assert check_winner(new_board()) is None

    def test_horizontal_win(self):
        board = new_board()
        for x in range(5):
            board[0][x] = 1
        assert check_winner(board) == 1

    def test_vertical_win(self):
        board = new_board()
        for y in range(5):
            board[y][0] = 2
        assert check_winner(board) == 2

    def test_diagonal_win(self):
        board = new_board()
        for i in range(5):
            board[i][i] = 1
        assert check_winner(board) == 1

    def test_anti_diagonal_win(self):
        board = new_board()
        for i in range(5):
            board[i][BOARD_SIZE - 1 - i] = 2
        assert check_winner(board) == 2

    def test_four_not_enough(self):
        board = new_board()
        for x in range(4):
            board[0][x] = 1
        assert check_winner(board) is None


# ---------------------------------------------------------------------------
# candidate_moves
# ---------------------------------------------------------------------------

class TestCandidateMoves:
    def test_empty_board_center(self):
        board = new_board()
        moves = candidate_moves(board)
        mid = BOARD_SIZE // 2
        assert moves == [(mid, mid)]

    def test_near_existing_stones(self):
        board = new_board()
        board[7][7] = 1
        moves = candidate_moves(board)
        assert len(moves) > 0
        assert (7, 7) not in moves
        assert all(0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE for x, y in moves)


# ---------------------------------------------------------------------------
# longest_line_score / move_score
# ---------------------------------------------------------------------------

class TestScoring:
    def test_longest_line_score_isolated(self):
        board = new_board()
        board[7][7] = 1
        score = longest_line_score(board, 7, 7, 1)
        assert score > 0

    def test_move_score_winning_move(self):
        board = new_board()
        for x in range(4):
            board[0][x] = 1
        score = move_score(board, 4, 0, 1)
        assert score == 1_000_000

    def test_move_score_block_opponent(self):
        board = new_board()
        for x in range(4):
            board[0][x] = 2
        score = move_score(board, 4, 0, 1)
        assert score >= 900_000

    def test_move_score_occupied_returns_minus_one(self):
        board = new_board()
        board[0][0] = 1
        assert move_score(board, 0, 0, 2) == -1


# ---------------------------------------------------------------------------
# is_turn_user
# ---------------------------------------------------------------------------

class TestIsTurnUser:
    def test_black_turn(self):
        game = {"turn": 1, "black_id": 10, "white_id": 20}
        assert is_turn_user(game, 10) is True
        assert is_turn_user(game, 20) is False

    def test_white_turn(self):
        game = {"turn": 2, "black_id": 10, "white_id": 20}
        assert is_turn_user(game, 20) is True
        assert is_turn_user(game, 10) is False


# ---------------------------------------------------------------------------
# player_name
# ---------------------------------------------------------------------------

class TestPlayerName:
    def test_human(self):
        game = {"black_id": 1, "white_id": 2}
        assert player_name(game, 1) == "<@1>"

    def test_ai(self):
        game = {"black_id": AI_PLAYER_ID, "white_id": 2}
        assert player_name(game, 1) == "AI"

    def test_draw(self):
        game = {"black_id": 1, "white_id": 2}
        assert player_name(game, None) == "引き分け"


# ---------------------------------------------------------------------------
# resolve_first_choice
# ---------------------------------------------------------------------------

class TestResolveFirstChoice:
    def test_explicit_black(self):
        choice, randomized = resolve_first_choice("black")
        assert choice == "black"
        assert randomized is False

    def test_explicit_white(self):
        choice, randomized = resolve_first_choice("white")
        assert choice == "white"
        assert randomized is False

    def test_random(self):
        choice, randomized = resolve_first_choice("random")
        assert choice in ("black", "white")
        assert randomized is True


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

class TestKeyHelpers:
    def test_coin_key(self):
        assert coin_key(1, 2) == "community_coin:1:2"

    def test_gomoku_index_key(self):
        assert gomoku_index_key(5) == "gomoku_games_index:5"

    def test_gomoku_game_key(self):
        assert gomoku_game_key(5, "abc") == "gomoku_game:5:abc"


# ---------------------------------------------------------------------------
# game_status_text
# ---------------------------------------------------------------------------

class TestGameStatusText:
    def test_basic(self):
        game = {"turn": 1, "black_id": 1, "white_id": 2, "bet": 0}
        text = game_status_text(game)
        assert "黒番" in text

    def test_with_difficulty(self):
        game = {"turn": 1, "black_id": 1, "white_id": AI_PLAYER_ID, "difficulty": "hard", "bet": 10}
        text = game_status_text(game)
        assert "上級" in text
        assert "10" in text

    def test_pending_white(self):
        game = {"turn": 1, "black_id": 1, "white_id": None, "bet": 0}
        text = game_status_text(game)
        assert "未参加" in text
