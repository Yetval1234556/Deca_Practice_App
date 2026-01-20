#!/usr/bin/env python3
import sys
import re
sys.path.insert(0, '.')
import importlib
import app
importlib.reload(app)
from app import COMMON_FIXES, ADDITIONAL_FIXES

test = 'cred It'
text = test

# Simulate step 1: COMMON_FIXES
for pattern, replacement in COMMON_FIXES:
    def preserve_case(m, repl=replacement):
        match_text = m.group(0)
        if match_text.isupper():
            return repl.upper()
        if match_text and match_text[0].isupper():
            return repl[0].upper() + repl[1:]
        return repl
    text = pattern.sub(preserve_case, text)

print(f'After COMMON_FIXES: "{text}"')

# Step 2: Hyphenation
text = re.sub(r'(\w)\s+-(\w)', r'\1-\2', text)
text = re.sub(r'(\w)-\s+(\w)', r'\1-\2', text)
text = re.sub(r'(\w)\s+-\s+(\w)', r'\1-\2', text)
print(f'After hyphenation: "{text}"')

# Step 3: Punctuation
text = re.sub(r'(\w),(\w)', r'\1, \2', text)
text = re.sub(r'\s+([.,;:!?])', r'\1', text)
text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
print(f'After punctuation: "{text}"')

# Step 4: Double spaces
text = re.sub(r'\s{2,}', ' ', text)
print(f'After double spaces: "{text}"')

# Step 4.6: ADDITIONAL_FIXES
for pattern, replacement in ADDITIONAL_FIXES:
    text = pattern.sub(replacement, text)
print(f'After ADDITIONAL_FIXES: "{text}"')

# Step 5: merge_prefix_careful
valid_short = {'a', 'i', 'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 
    'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 
    'us', 'we', 'a.', 'b.', 'c.', 'd.', 'e.', 're', 'vs', 'ok', 'ex'}

def merge_prefix_careful(match):
    p, w = match.group(1), match.group(2)
    if p.lower() in valid_short: 
        return match.group(0)
    return p + w

text = re.sub(r"(?<!')\b([a-zA-Z]{1,2})\s+([a-zA-Z]{3,})\b", merge_prefix_careful, text)
print(f'After merge_prefix: "{text}"')

# Step 5b: merge_suffix_smart
common_word_starts = {
    'h': {'as', 'is', 'er', 'im', 'ad', 'ave', 'ow', 'ere', 'eld'},
    'w': {'as', 'ith', 'ill', 'ere', 'hy', 'hen', 'hat', 'ho', 'ay', 'ould', 'ant'},
    't': {'he', 'his', 'hat', 'hen', 'hey', 'hem', 'here', 'hose', 'hus', 'heir'},
}

def merge_suffix_smart(match):
    w, s = match.group(1), match.group(2)
    full_text = match.group(0)
    
    if s.lower() in valid_short: 
        return full_text
    if s in {'A','B','C','D','E'}: 
        return full_text
        
    if len(s) == 1:
        letter = s.lower()
        if letter in common_word_starts:
            return full_text
        if letter not in {'s', 'd', 'r', 'n', 't', 'l', 'e', 'k', 'p', 'g', 'm'}: 
            return full_text
    return w + s

text = re.sub(r'\b([a-zA-Z]{2,})\s+([a-zA-Z]{1,2})\b', merge_suffix_smart, text)
print(f'After merge_suffix: "{text}"')
