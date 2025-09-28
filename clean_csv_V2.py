import csv
from pathlib import Path
from datetime import datetime

def is_valid_number(s):
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False

def clean_and_split_logs(input_file):
    input_file = Path(input_file)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = input_file.stem

    output_unified = input_file.with_name(f"{base_name}_unified_{timestamp_str}.csv")
    output_preprocess = input_file.with_name(f"{base_name}_preprocess_{timestamp_str}.csv")

    with open(input_file, "r", newline="", encoding="utf-8") as infile:
        reader = csv.reader(infile)
        rows = list(reader)

    if len(rows) < 2:
        raise ValueError("Input file too short to process.")

    # Find the most common field structure in DATA lines
    field_patterns = {}
    
    for row in rows[1:]:
        if len(row) == 2:
            raw_line = row[1].strip().strip('"')
            if raw_line.startswith("DATA:"):
                raw_data = raw_line[len("DATA:"):]
                fields = raw_data.split(",")
                
                field_keys = []
                all_valid = True
                
                for field in fields:
                    if "=" in field:
                        parts = field.split("=", 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            field_keys.append(key)
                        else:
                            all_valid = False
                            break
                    else:
                        all_valid = False
                        break
                
                if all_valid and field_keys:
                    key_tuple = tuple(field_keys)
                    field_patterns[key_tuple] = field_patterns.get(key_tuple, 0) + 1

    if not field_patterns:
        raise ValueError("No valid DATA: lines found to extract fields.")

    # Use the most common field pattern
    field_names = list(max(field_patterns.items(), key=lambda x: x[1])[0])
    print(f"Using field pattern: {field_names} (found in {field_patterns[tuple(field_names)]} lines)")
    
    # Report other patterns found
    if len(field_patterns) > 1:
        print("Other patterns found:")
        for pattern, count in field_patterns.items():
            if pattern != tuple(field_names):
                print(f"  {list(pattern)}: {count} lines")

    allowed_keys = set(field_names)

    unified_rows = [rows[0]]
    preprocess_header = ["Time"] + field_names
    raw_preprocess_rows = [preprocess_header]
    
    # Statistics
    stats = {
        "total_lines": len(rows) - 1,
        "data_lines": 0,
        "valid_data_lines": 0,
        "skipped_wrong_fields": 0,
        "skipped_malformed": 0,
        "cmd_lines": 0,
        "other_lines": 0
    }

    for row in rows[1:]:
        if len(row) != 2:
            stats["other_lines"] += 1
            continue
            
        time_str = row[0]
        raw_line = row[1].strip().strip('"')
        
        if raw_line.startswith("DATA:"):
            stats["data_lines"] += 1
            raw_data = raw_line[len("DATA:"):]
            fields = raw_data.split(",")
            
            # Create a dictionary of key-value pairs
            data_dict = {}
            valid = True
            
            for field in fields:
                if "=" in field:
                    parts = field.split("=", 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip()
                        data_dict[key] = val
                    else:
                        valid = False
                        break
                else:
                    valid = False
                    break
            
            if not valid:
                stats["skipped_malformed"] += 1
                continue
            
            # Check if all required fields are present
            if not all(key in data_dict for key in field_names):
                stats["skipped_wrong_fields"] += 1
                continue
            
            # Extract values in the correct order
            numeric_values = []
            for key in field_names:
                val = data_dict.get(key, "0")
                if not is_valid_number(val):
                    valid = False
                    break
                numeric_values.append(val)
            
            if valid:
                stats["valid_data_lines"] += 1
                raw_preprocess_rows.append([time_str] + numeric_values)
                unified_rows.append([time_str, raw_line])
            else:
                stats["skipped_malformed"] += 1
                
        elif raw_line.startswith("CMD:"):
            stats["cmd_lines"] += 1
            unified_rows.append([time_str, raw_line])
        else:
            stats["other_lines"] += 1
            unified_rows.append([time_str, raw_line])

    print("\nProcessing Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Anomaly detection with more robust handling
    def is_anomalous(idx):
        if idx == 0 or idx == len(raw_preprocess_rows) - 1:
            return False

        curr = raw_preprocess_rows[idx]
        prev = raw_preprocess_rows[idx - 1]
        next_ = raw_preprocess_rows[idx + 1]

        # Check T field (usually first numeric field)
        try:
            curr_t = float(curr[1])
            prev_t = float(prev[1])
            next_t = float(next_[1])
        except (ValueError, IndexError):
            return False

        # Check for time going backwards significantly
        if curr_t < prev_t - 1000:  # Allow small backwards jumps due to timing
            return True
            
        # Check for huge jumps
        if curr_t > prev_t + 100000 or curr_t > next_t + 100000:
            return True

        def ratio_check(a, b):
            if b == 0:
                return abs(a) > 1000
            ratio = max(a / b, b / a) if a > 0 and b > 0 else float('inf')
            return ratio > 100  # Increased threshold for more tolerance

        if ratio_check(curr_t, prev_t) or ratio_check(curr_t, next_t):
            return True

        return False

    filtered_preprocess_rows = [preprocess_header]
    anomalies_removed = 0

    for i in range(1, len(raw_preprocess_rows)):
        if not is_anomalous(i):
            filtered_preprocess_rows.append(raw_preprocess_rows[i])
        else:
            anomalies_removed += 1

    print(f"\nAnomalies removed: {anomalies_removed}")

    # Write output files
    with open(output_unified, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        for row in unified_rows:
            writer.writerow(row)

    with open(output_preprocess, "w", encoding="utf-8", newline="") as outfile:
        writer = csv.writer(outfile)
        for row in filtered_preprocess_rows:
            writer.writerow(row)

    return output_unified, output_preprocess

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <input_csv>")
        exit(1)

    input_path = sys.argv[1]
    try:
        unified_path, preprocess_path = clean_and_split_logs(input_path)
        print(f"\nOutput files:")
        print(f"  Unified log: {unified_path}")
        print(f"  Preprocessed data: {preprocess_path}")
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()