#!/usr/bin/env bash

# SPDX-FileCopyrightText: Tim Sutton
# SPDX-License-Identifier: MIT

# 🤖 Add a precommit hook that ensures that each python
# file is declared with the correct encoding
# -*- coding: utf-8 -*-

for file in $(git diff --cached --name-only --diff-filter=ACM | grep -E "\.py$"); do
    grep -q "^#.*coding[:=]\s*utf-8" "$file" || {
        echo "$file is missing UTF-8 encoding declaration"
        exit 1
    }
done
