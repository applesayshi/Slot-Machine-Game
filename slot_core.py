"""Core slot machine rules, shared by the console game and the pygame UI.

Nothing in here knows how the game is displayed. Both front-ends import these
values and functions, so the odds and payouts can never drift apart.
"""

import random

# One line is the top line, 2 is the top 2 lines, 3 is all 3 lines. This is to keep things simple for this project
MAX_LINES = 3
MAX_BET = 100
MIN_BET = 1

ROWS = 3
COLS = 3

# Symbols for the slot machine, A being the most valuable (and least common)
symbol_count = {
    "A": 2,
    "B": 4,
    "C": 6,
    "D": 8
}

# Multiplier that follows online slot machine rates. Mathematically correct to real life applications
symbol_value = {
    "A": 300,
    "B": 35,
    "C": 9,
    "D": 2
}


def check_winnings(columns, lines, bet, values):
    winnings = 0
    winning_lines = []
    # loop through each row
    # Note: Columns looks like: [[1, 2, 3], [1, 2, 3], [1, 2, 3]]
    for line in range(lines):
        symbol = columns[0][line]  # symbol that needs to be identical = to the first symbol in first column of that row
        for column in columns:  # check each column to see if symbol is equal
            symbol_to_check = column[line]
            if symbol != symbol_to_check:
                break
        else:
            # all symbols are the same, so user wins. Bet is the bet on each line, not the total bet.
            winnings += values[symbol] * bet
            winning_lines.append(line + 1)

    return winnings, winning_lines


def get_slot_machine_spin(rows, cols, symbols):
    # Randomly pick number of symbols in each column
    # Appending each symbol the specified number of times from symbol_count
    # Note: Not the most time or space efficient. Fine for small values, but will possibly break for large/complex cases
    all_symbols = []
    for symbol, count in symbols.items():
        for _ in range(count):
            all_symbols.append(symbol)
    columns = []

    # Need to create a copy of all_symbols, as we need to remove symbols from the list as we add it into the columns
    # This is because we can only add 2 As, if we added 3, it would defeat the purpose.
    for _ in range(cols):
        column = []
        current_symbols = all_symbols[:]
        for _ in range(rows):
            value = random.choice(current_symbols)
            current_symbols.remove(value)
            column.append(value)
        columns.append(column)
    return columns
