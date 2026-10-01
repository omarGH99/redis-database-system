"""
generate_data.py
-----------------
Generates synthetic CSVs for every domain in the project: students,
universities, courses, enrollments, hospitals, businesses, properties,
government agencies and events.

The repo already ships ready-made CSVs in ./data, so you only need this
script if you want to regenerate them (requires `pip install faker`).
The loader picks up whichever files are present.
"""

import csv
import random
from pathlib import Path
from faker import Faker

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

fake = Faker()
Faker.seed(42)
random.seed(42)

# ------------------------------------------------------------------
# Domain vocabularies (Kurdistan / Iraq flavored where appropriate)
# ------------------------------------------------------------------
UNIVERSITIES = [
    ("UNI001", "American University of Kurdistan",       "Duhok",     "Private", 2014),
    ("UNI002", "University of Kurdistan Hewler",         "Erbil",     "Private", 2006),
    ("UNI003", "University of Duhok",                    "Duhok",     "Public",  1992),
    ("UNI004", "Salahaddin University",                  "Erbil",     "Public",  1968),
    ("UNI005", "University of Sulaimani",                "Sulaymaniyah", "Public", 1968),
    ("UNI006", "Tishk International University",         "Erbil",     "Private", 2008),
    ("UNI007", "Komar University of Science and Technology", "Sulaymaniyah", "Private", 2013),
    ("UNI008", "Cihan University",                       "Erbil",     "Private", 2007),
]

COURSE_CATALOG = [
    ("Deep Learning 101",           "Computer Science", 3),
    ("Machine Learning",            "Computer Science", 3),
    ("Database Systems",            "Computer Science", 3),
    ("Data Structures",             "Computer Science", 4),
    ("Algorithms",                  "Computer Science", 3),
    ("Web Development",             "Computer Science", 3),
    ("Operating Systems",           "Computer Science", 3),
    ("Computer Networks",           "Computer Science", 3),
    ("Software Engineering",        "Computer Science", 3),
    ("Calculus I",                  "Mathematics",      4),
    ("Linear Algebra",              "Mathematics",      3),
    ("Statistics",                  "Mathematics",      3),
    ("Microeconomics",              "Economics",        3),
    ("Macroeconomics",              "Economics",        3),
    ("Financial Accounting",        "Business",         3),
    ("Marketing Principles",        "Business",         3),
    ("Organic Chemistry",           "Chemistry",        4),
    ("Human Anatomy",               "Medicine",         4),
    ("Civil Engineering Materials", "Civil Engineering", 3),
    ("English Composition",         "English",          3),
]

INSTRUCTORS = [
    "Dr. Dara Sherwani", "Dr. Aram Hassan", "Dr. Lana Mohammed",
    "Dr. Bawan Ali", "Dr. Shilan Ahmed", "Dr. Karwan Saleh",
    "Dr. Niga Rasul", "Dr. Hawre Khalid", "Dr. Zhino Jamal",
    "Dr. Rebwar Mahmood",
]

HOSPITAL_NAMES = [
    "Azadi Teaching Hospital", "Hevi Pediatric Hospital", "Duhok Emergency Hospital",
    "Rizgary Teaching Hospital", "West Erbil Emergency", "Shar Hospital",
    "Sulaymaniyah General", "PAR Private Hospital", "Zheen International Hospital",
    "CMC Hospital",
]

BUSINESS_TYPES = [
    "Restaurant", "Cafe", "Retail Store", "Tech Startup", "Manufacturing",
    "Construction", "Logistics", "Consultancy", "Pharmacy", "Supermarket",
]

PROPERTY_TYPES = ["Apartment", "Villa", "Commercial Office", "Land Plot", "Townhouse"]

GOV_AGENCIES = [
    ("GOV001", "Ministry of Education",           "Education"),
    ("GOV002", "Ministry of Health",              "Health"),
    ("GOV003", "Ministry of Higher Education",    "Education"),
    ("GOV004", "Ministry of Interior",            "Security"),
    ("GOV005", "Ministry of Finance",             "Finance"),
    ("GOV006", "Ministry of Trade and Industry",  "Economy"),
    ("GOV007", "Ministry of Agriculture",         "Agriculture"),
]

EVENT_TYPES = ["Conference", "Workshop", "Seminar", "Cultural Festival", "Job Fair", "Sports Tournament"]

CITIES = ["Duhok", "Erbil", "Sulaymaniyah", "Halabja", "Zakho", "Akre", "Soran"]


# ------------------------------------------------------------------
# Generators
# ------------------------------------------------------------------
def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {len(rows):>5} rows -> {path.name}")


def gen_universities():
    rows = [(u_id, name, city, kind, founded) for u_id, name, city, kind, founded in UNIVERSITIES]
    write_csv(DATA_DIR / "universities.csv",
              ["university_id", "name", "city", "type", "founded_year"], rows)


def gen_courses(n=60):
    rows = []
    for i in range(1, n + 1):
        title, dept, credits = random.choice(COURSE_CATALOG)
        u_id = random.choice(UNIVERSITIES)[0]
        rows.append((
            f"CRS{i:04d}",
            title,
            dept,
            credits,
            u_id,
            random.choice(INSTRUCTORS),
            random.choice(["Fall 2025", "Spring 2026"]),
        ))
    write_csv(DATA_DIR / "courses.csv",
              ["course_id", "title", "department", "credits", "university_id",
               "instructor", "semester"], rows)
    return rows


def gen_students(n=1000):
    rows = []
    for i in range(1, n + 1):
        u_id = random.choice(UNIVERSITIES)[0]
        rows.append((
            f"STU{i:05d}",
            fake.first_name(),
            fake.last_name(),
            random.randint(18, 28),
            random.choice(["Male", "Female"]),
            u_id,
            random.choice(["Computer Science", "Business", "Medicine",
                           "Civil Engineering", "Economics", "English",
                           "Mathematics", "Chemistry"]),
            random.choice([1, 2, 3, 4]),                     # year
            round(random.uniform(2.0, 4.0), 2),              # gpa
            random.choice(CITIES),
            fake.email(),
        ))
    write_csv(DATA_DIR / "students.csv",
              ["student_id", "first_name", "last_name", "age", "gender",
               "university_id", "major", "year", "gpa", "city", "email"], rows)
    return rows


def gen_enrollments(students, courses, avg_per_student=4):
    rows = []
    enrol_id = 1
    course_ids = [c[0] for c in courses]
    for s in students:
        picks = random.sample(course_ids, k=min(avg_per_student, len(course_ids)))
        for c_id in picks:
            rows.append((
                f"ENR{enrol_id:06d}",
                s[0],            # student_id
                c_id,            # course_id
                random.choice(["A", "A-", "B+", "B", "B-", "C+", "C", "D", "F", "IP"]),
                random.choice(["Fall 2025", "Spring 2026"]),
            ))
            enrol_id += 1
    write_csv(DATA_DIR / "enrollments.csv",
              ["enrollment_id", "student_id", "course_id", "grade", "semester"], rows)


def gen_hospitals(n=30):
    rows = []
    for i in range(1, n + 1):
        rows.append((
            f"HOS{i:04d}",
            random.choice(HOSPITAL_NAMES) + (f" #{i}" if i > len(HOSPITAL_NAMES) else ""),
            random.choice(CITIES),
            random.choice(["Public", "Private"]),
            random.randint(50, 800),                    # beds
            random.randint(20, 200),                    # doctors
            round(random.uniform(2.5, 5.0), 1),         # rating
            random.choice(["General", "Pediatric", "Cardiac", "Emergency", "Teaching"]),
        ))
    write_csv(DATA_DIR / "hospitals.csv",
              ["hospital_id", "name", "city", "type", "beds", "doctors",
               "rating", "specialty"], rows)


def gen_businesses(n=200):
    rows = []
    for i in range(1, n + 1):
        rows.append((
            f"BUS{i:05d}",
            fake.company(),
            random.choice(BUSINESS_TYPES),
            random.choice(CITIES),
            random.randint(2005, 2025),                  # founded
            random.randint(2, 500),                      # employees
            round(random.uniform(50_000, 5_000_000), 2), # revenue
        ))
    write_csv(DATA_DIR / "businesses.csv",
              ["business_id", "name", "type", "city", "founded_year",
               "employees", "annual_revenue"], rows)


def gen_properties(n=300):
    rows = []
    for i in range(1, n + 1):
        rows.append((
            f"PRP{i:05d}",
            random.choice(PROPERTY_TYPES),
            random.choice(CITIES),
            random.randint(50, 600),                       # area_m2
            random.randint(1, 7),                          # bedrooms
            round(random.uniform(40_000, 950_000), 2),     # price_usd
            random.choice(["For Sale", "For Rent", "Sold"]),
        ))
    write_csv(DATA_DIR / "properties.csv",
              ["property_id", "type", "city", "area_m2", "bedrooms",
               "price_usd", "status"], rows)


def gen_government():
    rows = [(gid, name, sector, random.randint(500, 25000),
             round(random.uniform(10_000_000, 500_000_000), 2))
            for gid, name, sector in GOV_AGENCIES]
    write_csv(DATA_DIR / "government.csv",
              ["agency_id", "name", "sector", "employees", "annual_budget"], rows)


def gen_events(n=80):
    rows = []
    for i in range(1, n + 1):
        rows.append((
            f"EVT{i:04d}",
            fake.catch_phrase(),
            random.choice(EVENT_TYPES),
            random.choice(CITIES),
            fake.date_between(start_date="-1y", end_date="+6M").isoformat(),
            random.randint(20, 5000),                       # attendees
            random.choice([u[0] for u in UNIVERSITIES] + ["GOV001", "GOV002", "BUS00001"]),
        ))
    write_csv(DATA_DIR / "events.csv",
              ["event_id", "title", "type", "city", "date",
               "attendees", "organizer_id"], rows)


def main():
    print(f"Generating synthetic CSVs into {DATA_DIR}/ ...")
    gen_universities()
    courses = gen_courses(60)
    students = gen_students(1000)
    gen_enrollments(students, courses, avg_per_student=4)
    gen_hospitals(30)
    gen_businesses(200)
    gen_properties(300)
    gen_government()
    gen_events(80)
    print("Done.")


if __name__ == "__main__":
    main()
