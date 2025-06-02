import re
import timeit

# 1. Define TestLoc class
class TestLoc:
    def __init__(self, id_val, name, line):
        self.id_val = id_val
        self.name = name
        self.line = line

    def __repr__(self):
        return f"TestLoc(id='{self.id_val}', name='{self.name}', line={self.line})"

# 2. Define LOC_PATTERN for finding locations in CLEANED content
LOC_PATTERN = re.compile(r"^\s*:([^\n]+)", re.MULTILINE)

# Helper function to clean a name string of line comments
def strip_trailing_comments_for_matching(name_str):
    name_str = name_str.split('//', 1)[0]
    name_str = name_str.split(';', 1)[0]
    name_str = name_str.split('&', 1)[0] # Added &
    name_str = name_str.split('#', 1)[0]
    return name_str.strip()

# 3. Implement prep_content_silent (updated for & delimiter)
def prep_content_silent(content):
    """
    Prepares content for parsing by:
    1. Removing block comments (/* ... */) from the entire content.
    2. Applying user's line joining rule: \n\s*_ is removed.
    3. For each resulting line:
        a. Removing line comments (//, then ;, then &, then #).
        b. Stripping whitespace from the line.
    4. Filtering out empty lines.
    """
    content_no_block_comments = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content_joined = re.sub(r'\n\s*_', '', content_no_block_comments)

    processed_lines = []
    for line in content_joined.split('\n'):
        line = line.split('//', 1)[0] # C-style line comments
        line = line.split(';', 1)[0]  # Semicolon comments
        line = line.split('&', 1)[0]  # Ampersand delimiter/comment
        line = line.split('#', 1)[0]  # Hash comments
        line = line.strip()
        if line:
            processed_lines.append(line)
    return '\n'.join(processed_lines)

# 4. Your parse_locations_only_lines2_silent function (updated matching logic)
def parse_locations_only_lines2_silent(orig_content):
    """
    Version 2.3: Handles '&' as a delimiter and simplifies matching rules.
    """
    clean_content = prep_content_silent(orig_content)
    resolved_loc_objects = []
    clean_matches_from_parser = list(LOC_PATTERN.finditer(clean_content))

    orig_potential_locs = []
    current_char_offset_in_original = 0
    original_lines_for_iteration = orig_content.split('\n')

    for line_num_1based, line_str_from_original in enumerate(original_lines_for_iteration, 1):
        for match_in_original_line in re.finditer(r':([^\n]*)', line_str_from_original):
            text_after_colon_original = match_in_original_line.group(1)
            
            # raw_name_for_matching_base: text after colon, block comments removed, then .strip()
            raw_name_for_matching_base = re.sub(r'/\*.*?\*/', '', text_after_colon_original, flags=re.DOTALL).strip()

            # We store this base version. It will be further cleaned by strip_trailing_comments_for_matching
            # during the matching phase. If empty after this base cleaning, skip.
            if not raw_name_for_matching_base: 
                # Check if text_after_colon_original itself becomes empty after full cleaning
                # to avoid adding empty potential locs that only had comments.
                if not strip_trailing_comments_for_matching(text_after_colon_original.strip()): # check full clean
                    continue
            
            abs_colon_start_char_idx = current_char_offset_in_original + match_in_original_line.start()
            
            orig_potential_locs.append({
                "raw_name_base": raw_name_for_matching_base, # text after ':', no /*..*/, stripped
                "char_start": abs_colon_start_char_idx,
                "line_num": line_num_1based,
            })
        current_char_offset_in_original += len(line_str_from_original) + 1

    orig_potential_locs.sort(key=lambda x: x["char_start"])
    
    last_successfully_mapped_orig_pot_idx = -1

    for i, clean_match_object in enumerate(clean_matches_from_parser):
        canonical_clean_loc_name = clean_match_object.group(1).strip()
        determined_original_line_num = -1
        found_match_for_this_clean_loc = False

        for current_pot_idx in range(last_successfully_mapped_orig_pot_idx + 1, len(orig_potential_locs)):
            potential_loc_from_original = orig_potential_locs[current_pot_idx]
            
            # Get the base name (no block comments, stripped)
            orig_cand_base = potential_loc_from_original["raw_name_base"]
            # Fully clean it using the same line comment logic as prep_content_silent
            orig_cand_fully_cleaned = strip_trailing_comments_for_matching(orig_cand_base)

            # If fully cleaned original candidate is empty, it cannot match anything.
            if not orig_cand_fully_cleaned:
                continue

            # Rule A: Exact match of fully cleaned names
            if canonical_clean_loc_name == orig_cand_fully_cleaned:
                determined_original_line_num = potential_loc_from_original["line_num"]
                last_successfully_mapped_orig_pot_idx = current_pot_idx
                found_match_for_this_clean_loc = True
                break
            
            # Rule B: Clean name starts with fully cleaned original name (for line continuation)
            # This rule should only apply if the names are not an exact match but orig is a prefix.
            if canonical_clean_loc_name.startswith(orig_cand_fully_cleaned):
                determined_original_line_num = potential_loc_from_original["line_num"]
                last_successfully_mapped_orig_pot_idx = current_pot_idx
                found_match_for_this_clean_loc = True
                break
        
        if not found_match_for_this_clean_loc:
            char_start_in_clean = clean_match_object.start()
            fallback_line_num = clean_content[:char_start_in_clean].count('\n') + 1
            determined_original_line_num = fallback_line_num

        resolved_loc_objects.append(TestLoc(id_val=str(i), name=canonical_clean_loc_name, line=determined_original_line_num))

    return resolved_loc_objects


# 5. Main execution block
if __name__ == "__main__":
    input_content_simple_ampersand = """:new
:new_amp&sdsfs
:another_loc ; with semicolon
:final//with_c_comment
"""
    print(f"Input Content (Simple Ampersand Test):\n'''\n{input_content_simple_ampersand}'''\n")
    # cleaned_simple = prep_content_silent(input_content_simple_ampersand)
    # print(f"Cleaned Content by prep_content_silent:\n'''\n{cleaned_simple}'''\n")
    locations_simple = parse_locations_only_lines2_silent(input_content_simple_ampersand)
    print(f"Found {len(locations_simple)} locations:")
    for loc in locations_simple:
        print(f"  Location: {loc.name} (Original Line: {loc.line}, ID: {loc.id_val})")
    print("-" * 30)

    input_content_2 = """/* comment */:ne/* dfsdf*/w;comment
:new;comment & also ampersand comment
p/* comment*/l/* _ sdfsd */n hello, world ; and thanks for all the fish!
/*
*/
:erff&if a then :dfs else dfs
;pln new line
pln hi!
end/*
*/
:ne
_w_loc/*sdfsf */ & and more stuff
proc 
_old_loc
end
:000&comment_after_amp
gotoloc1
goto loc2
if a = 10 then b = 40 & if z = 5 and b = 10 then goto z else goto hell
end
"""
    print(f"Input Content (Complex Test):\n'''\n{input_content_2}'''\n")
    
    # --- You can uncomment these lines to see the intermediate cleaned content ---
    # cleaned_for_debug = prep_content_silent(input_content_2)
    # print(f"Cleaned Content by prep_content_silent:\n'''\n{cleaned_for_debug}'''\n")
    # ---
    
    locations = parse_locations_only_lines2_silent(input_content_2)

    print(f"Found {len(locations)} locations:")
    for loc in locations:
        print(f"  Location: {loc.name} (Original Line: {loc.line}, ID: {loc.id_val})")

    # Timing the function
    num_executions = 1000
    time_taken = timeit.timeit(lambda: parse_locations_only_lines2_silent(input_content_2), number=num_executions)
    
    print(f"\nTiming for {num_executions} executions:")
    print(f"Total time: {time_taken:.4f} seconds")
    print(f"Average time per execution: {time_taken/num_executions:.6f} seconds")