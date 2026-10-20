"""Reviewed source strings for offline worker integration, never imported as code."""
REFERENCE_SOURCES = {
    'sum_even': 'def sum_even(numbers):\n    return sum(n for n in numbers if n % 2 == 0)\n',
    'clamp': 'def clamp(value, lower, upper):\n    return max(lower, min(value, upper))\n',
    'palindrome': "def is_palindrome(text):\n    clean = ''.join(c.lower() for c in text if c.isalnum())\n    return clean == clean[::-1]\n",
    'unique_order': 'def unique_order(numbers):\n    result = []\n    for number in numbers:\n        if number not in result:\n            result.append(number)\n    return result\n',
    'count_words': 'def count_words(text):\n    counts = {}\n    for word in text.split():\n        counts[word] = counts.get(word, 0) + 1\n    return counts\n',
}

INCORRECT = 'def sum_even(numbers):\n    return 0\n'
EXCEPTION = 'def sum_even(numbers):\n    return 1 // 0\n'
INFINITE = 'def sum_even(numbers):\n    for n in range(1000000000000):\n        pass\n    return 0\n'
MUTATING = 'def sum_even(numbers):\n    numbers.append(99)\n    return sum(n for n in numbers if n % 2 == 0)\n'
FALSIFYING = 'def sum_even(numbers):\n    print("{\\"passed\\":true}")\n    return 0\n'
ALIASED_EVAL = 'def sum_even(numbers):\n    sum = eval\n    return sum("6")\n'
BAD_RESULT = 'def sum_even(numbers):\n    return set(numbers)\n'
