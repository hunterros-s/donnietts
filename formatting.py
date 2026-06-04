ORDINAL_DAYS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
    13: "thirteenth",
    14: "fourteenth",
    15: "fifteenth",
    16: "sixteenth",
    17: "seventeenth",
    18: "eighteenth",
    19: "nineteenth",
    20: "twentieth",
    21: "twenty first",
    22: "twenty second",
    23: "twenty third",
    24: "twenty fourth",
    25: "twenty fifth",
    26: "twenty sixth",
    27: "twenty seventh",
    28: "twenty eighth",
    29: "twenty ninth",
    30: "thirtieth",
    31: "thirty first",
}

ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]

TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(n):
    n = int(n)
    if n < 0:
        return "minus " + number_to_words(abs(n))
    if n < 20:
        return ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return TENS[tens] if ones == 0 else f"{TENS[tens]} {ONES[ones]}"

    hundreds, rest = divmod(n, 100)
    if rest == 0:
        return f"{ONES[hundreds]} hundred"
    return f"{ONES[hundreds]} hundred {number_to_words(rest)}"


def time_to_words(now):
    hour = now.hour % 12 or 12
    minute = now.minute
    am_pm = "A M" if now.hour < 12 else "P M"

    if minute == 0:
        return f"{number_to_words(hour)} o'clock {am_pm}"
    if minute < 10:
        return f"{number_to_words(hour)} oh {number_to_words(minute)} {am_pm}"
    return f"{number_to_words(hour)} {number_to_words(minute)} {am_pm}"


def date_to_words(now):
    return f"{now.strftime('%B')} {ORDINAL_DAYS[now.day]}"


def percent_to_words(percent):
    return f"{number_to_words(percent)} percent"


def optional_number_to_words(value):
    return number_to_words(value) if value is not None else ""


def optional_percent_to_words(value):
    return percent_to_words(value) if value is not None else ""


def wind_to_words(mph):
    if mph < 1:
        return "calm wind"
    if mph < 8:
        return "light wind"
    if mph < 18:
        return "moderate wind"
    if mph < 31:
        return "breezy conditions"
    return "strong wind"
