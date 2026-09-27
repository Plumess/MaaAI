"""Split renderer labels by normalized text, repeatably across corpus directories."""
import argparse
import hashlib
import unicodedata
from pathlib import Path


def train_test_split(labels, train_ratio=0.8, seed=20260921):
    if not 0 < train_ratio < 1:
        raise ValueError('train_ratio must be between 0 and 1')
    train, test = [], []
    seen = set()
    for line in labels:
        identifier, separator, text = line.rstrip('\r\n').partition(' ')
        if not separator or not identifier or not text.strip():
            raise ValueError(f'malformed renderer label: {line!r}')
        if identifier in seen:
            raise ValueError(f'duplicate image identifier: {identifier}')
        seen.add(identifier)
        # NFC preserves distinctions such as full-width characters. Do not use NFKC.
        # Hash the text, not the filename: renderings of one label in different
        # corpus folders must stay in the same split. Keep the stored label intact.
        group = unicodedata.normalize('NFC', text.replace('\u00a0', ' '))
        value = int.from_bytes(hashlib.sha256(f'{seed}\0{group}'.encode()).digest()[:8], 'big')
        (train if value / 2**64 < train_ratio else test).append(line.rstrip('\r\n') + '\n')
    return train, test


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_labels', type=Path)
    parser.add_argument('--output', '-o', required=True, type=Path)
    parser.add_argument('--train_ratio', '-t', type=float, default=.8)
    parser.add_argument('--seed', type=int, default=20260921)
    args = parser.parse_args()
    train, test = train_test_split(args.input_labels.read_text(encoding='utf-8').splitlines(True), args.train_ratio, args.seed)
    if not train or not test:
        raise ValueError('empty split: provide more independent text groups, not a different seed to improve scores')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows in [('train.txt', train), ('test.txt', test)]:
        (args.output/name).write_text(''.join(rows), encoding='utf-8')
    print(f'train={len(train)}, dev={len(test)}; text-group split, seed={args.seed}')


if __name__ == '__main__':
    main()
