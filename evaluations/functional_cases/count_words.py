def count_words(text):
    counts = {}
    for word in text.split():
        counts[word] = 1
    return counts
