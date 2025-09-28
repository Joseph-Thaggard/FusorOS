import csv
from pathlib import Path
from datetime import datetime

def is_valid_number(s):
    try:
        float(s)
        return True
    except ValueError:
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

    # Extract field names from first valid DATA line
    field_names = []
    for row in rows[1:]:
        if len(row) == 2:
            raw_line = row[1].strip('"')
            if raw_line.startswith("DATA:"):
                raw_data = raw_line[len("DATA:"):]
                fields = raw_data.split(",")
                valid = True
                for field in fields:
                    if field.count("=") != 1:
                        valid = False
                        break
                    key, val = field.split("=", 1)
                    if not is_valid_number(val):
                        valid = False
                        break
                if valid:
                    field_names = [field.split("=")[0] for field in fields]
                    break

    if not field_names:
        raise ValueError("No valid DATA: lines found to extract fields.")

    allowed_keys = set(field_names)

    unified_rows = [rows[0]]
    preprocess_header = ["Time"] + field_names
    raw_preprocess_rows = [preprocess_header]

    for row in rows[1:]:
        if len(row) != 2:
            continue
        time_str = row[0]
        raw_line = row[1].strip('"')
        if raw_line.startswith("DATA:"):
            raw_data = raw_line[len("DATA:"):]
            fields = raw_data.split(",")
            # Validate count
            if len(fields) != len(field_names):
                # Skip lines with wrong number of fields
                continue

            valid = True
            numeric_values = []
            for field in fields:
                if field.count("=") != 1:
                    valid = False
                    break
                key, val = field.split("=", 1)
                if key not in allowed_keys:
                    valid = False
                    break
                if not is_valid_number(val):
                    valid = False
                    break
                numeric_values.append(val)

            if valid:
                raw_preprocess_rows.append([time_str] + numeric_values)
                unified_rows.append([time_str, raw_line])
            else:
                # skip malformed DATA line
                continue
        else:
            # Non-DATA lines (CMD etc) go always to unified
            unified_rows.append([time_str, raw_line])

    def is_anomalous(idx):
        if idx == 0 or idx == len(raw_preprocess_rows) - 1:
            return False

        curr = raw_preprocess_rows[idx]
        prev = raw_preprocess_rows[idx - 1]
        next_ = raw_preprocess_rows[idx + 1]

        try:
            curr_t = float(curr[1])
            prev_t = float(prev[1])
            next_t = float(next_[1])
        except Exception:
            return False

        def ratio_check(a, b):
            if b == 0:
                return abs(a) > 1000
            return max(a / b, b / a) > 10

        if ratio_check(curr_t, prev_t) or ratio_check(curr_t, next_t):
            return True

        return False

    filtered_preprocess_rows = [preprocess_header]

    for i in range(1, len(raw_preprocess_rows)):
        if not is_anomalous(i):
            filtered_preprocess_rows.append(raw_preprocess_rows[i])
        else:
            # Skipping anomalous row
            pass

    with open(output_unified, "w", encoding="utf-8", newline="") as outfile:
        for row in unified_rows:
            outfile.write(",".join(row) + "\n")

    with open(output_preprocess, "w", encoding="utf-8", newline="") as outfile:
        for row in filtered_preprocess_rows:
            outfile.write(",".join(row) + "\n")

    return output_unified, output_preprocess

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <input_csv>")
        exit(1)

    input_path = sys.argv[1]
    unified_path, preprocess_path = clean_and_split_logs(input_path)
    print(f"Unified log saved to: {unified_path}")
    print(f"Preprocessed data saved to: {preprocess_path}")

