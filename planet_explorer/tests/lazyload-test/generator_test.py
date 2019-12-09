import os
import itertools
import collections

TOP_ITEMS_PAGE = 9

top_item_count = 0
top_items = []

# insertNodes(0, [root])

path = '/'
# generate root node children
dir_list = [os.path.join(path, i) for i in os.listdir(path)]


# dir_gen = list(itertools.islice(dir_list, TOP_ITEMS_PAGE))
# def dir_gen():
#     yield iter(next(dir_list) for _ in range(TOP_ITEMS_PAGE))

print(f'dir_list: {dir_list}')


# START = 0
# def dir_gen():
#     stop = START + TOP_ITEMS_PAGE
#     dir_listing = list(itertools.islice(iter(dir_list), START, stop))
#     START = stop
#     yield dir_listing

# def consume(iterator, n=None):
#     "Advance the iterator n-steps ahead. If n is None, consume entirely."
#     # Use functions that consume iterators at C speed.
#     if n is None:
#         # feed the entire iterator into a zero-length deque
#         return collections.deque(iterator, maxlen=0)
#     else:
#         # advance to the empty slice starting at position n
#         return next(itertools.islice(iterator, n, n), None)

def dir_gen(iterator, count):
    itr = iter(iterator)
    while True:
        nexts = []
        for _ in range(count):
            try:
                nexts.append(next(itr))
            except StopIteration:
                break
        if nexts:
            yield nexts
        else:
            break


# dir_gen = itertools.islice(dir_list, TOP_ITEMS_PAGE, TOP_ITEMS_PAGE)

for dir_grp in dir_gen(dir_list, 10):
    print(list(dir_grp))
print('----')

# print(consume(dir_list, 10))
