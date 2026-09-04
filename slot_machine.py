"""The original text based slot machine. Run with: python3 slot_machine.py"""

from slot_core import (
    MAX_LINES,
    MAX_BET,
    MIN_BET,
    ROWS,
    COLS,
    symbol_count,
    symbol_value,
    check_winnings,
    get_slot_machine_spin,
)


# Transposing the matrix
# This function takes an inline version of the columns and rows (for example: [[], [], []], and prints it out into the column format
# Basically it says: print the first element of each columns, and repeat for the 2nd element, and 3rd element. 
def print_slot_machine(columns):
    for row in range(len(columns[0])):
        for i, column in enumerate(columns):
            if i != len(columns) - 1:
                print(column[row], end=" | ")
            else:
                print(column[row], end="")
        # For new line in the row
        print()


# Takes in the user input of "money"
def deposit():
    while True:
        amount = input("What would you like to deposit? $")
        if amount.isdigit():
            amount = int(amount)
            if amount > 0:
                break
            else:
                print("Amount must be greater than 0")
        else:
            print("Please enter a number")
    return amount


# Takes user input for number of lines to bet on
# Lines in this game are build top to bottom. So 1 line means only winning the top, 2 lines means top 2, 3 means top 3. User does not get to pick which line. 
def get_number_of_lines():
    while True:
        lines = input("Enter the number of lines to bet on (1-" + str(MAX_LINES) + ")? ")
        if lines.isdigit():
            lines = int(lines)
            # Check if number of inputted lines is within our bounds
            if 1 <= lines <= MAX_LINES:
                break
            else:
                print("Enter a valid number of lines")
        else:
            print("Please enter a number")
    return lines

# Simply gets the amount that person wants to bet per line
def get_bet():
    while True:
        bet = input("What would you like to bet on each line? $")
        if bet.isdigit():
            bet = int(bet)
            if MIN_BET <= bet <= MAX_BET:
                break
            else:
                print(f"Amount must be between ${MIN_BET} - ${MAX_BET}.")
        else:
            print("Please enter a number")

    return bet

# Balance, and also checks if user can bet specified amount. # of lines * bet gives total bet
def spin(balance):
    lines = get_number_of_lines()
    # Check if user can afford the bet
    while True:
        bet = get_bet()
        total_bet = bet * lines
        if total_bet > balance:
            print(f"You do not have enough money to bet that amount, your current balance is: ${balance}")
        else:
            break

    print(f"You are betting ${bet} on {lines} lines. Total bet is equal to: ${total_bet}")
    slots = get_slot_machine_spin(ROWS, COLS, symbol_count)
    print_slot_machine(slots)
    winnings, winning_lines = check_winnings(slots, lines, bet, symbol_value)
    print(f"You Won ${winnings}.")
    print(f"You won on lines:", *winning_lines)
    return winnings - total_bet


def main():
    balance = deposit()
    while True:
        # Updates the balance with winning/lost money
        print(f"Current balance is: ${balance}")
        answer = input("Press enter to play (q to quit).")
        if answer == "q":
            break
        balance += spin(balance)

    print(f"You left with ${balance}")

# This is a guard. Without this guard, python may run this file on importing from another file, which is not what we want. When Python initializes __name__, but its imported from another class, it wont be == to __main__, so this wont run. 
if __name__ == "__main__":
    main()
