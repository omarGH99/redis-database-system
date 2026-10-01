# Redis Schema Design

Redis is a key-value store, so "schema" really means **a disciplined naming
convention plus the right data structure per access pattern**. We chose
structures based on *how the data will be read* &mdash; not how it would look in
a relational table.

This document describes how the 13 CSVs in `data/` map onto
Redis keys.

## 1. Entity hashes (the "row")

Every record is stored as a Redis **HASH** under a typed key. The id column
in the CSV becomes the suffix of the key.

| Domain                | CSV file                              | Key pattern              | Example key            | id col           |
|-----------------------|----------------------------------------|--------------------------|------------------------|------------------|
| Universities          | `universities.csv`                     | `university:<id>`        | `university:UKH`       | `university_id`  |
| Departments           | `departments.csv`                      | `department:<id>`        | `department:D01`       | `dept_id`        |
| Courses               | `courses.csv`                          | `course:<id>`            | `course:C101`          | `course_id`      |
| Students              | `students.csv`                         | `student:<id>`           | `student:S001`         | `student_id`     |
| Enrollments           | `enrollments_1000.csv`                 | `enrollment:<id>`        | `enrollment:E001`      | `enroll_id`      |
| Hospitals             | `hospitals.csv`                        | `hospital:<id>`          | `hospital:H001`        | `hospital_id`    |
| Patients              | `patients_1000.csv`                    | `patient:<id>`           | `patient:P001`         | `patient_id`     |
| Companies             | `companies.csv`                        | `company:<id>`           | `company:CO01`         | `company_id`     |
| Properties            | `properties.csv`                       | `property:<id>`          | `property:R001`        | `property_id`    |
| Ministries            | `ministries.csv`                       | `ministry:<id>`          | `ministry:MOH`         | `ministry_id`    |
| Government projects   | `government_projects.csv`              | `project:<id>`           | `project:PJ01`         | `project_id`     |
| Events                | `events.csv`                           | `event:<id>`             | `event:EV01`           | `event_id`       |
| Event registrations   | `event_registrations_1000.csv`         | `registration:<id>`      | `registration:REG001`  | `registration_id`|

**Why hashes?** Each field is independently addressable (`HGET`, `HSET`),
so we don't pay JSON-parse cost on every read; field-level updates are
atomic; and memory footprint is excellent thanks to ziplist encoding for
small hashes.

## 2. Reverse indexes (sets)

Categorical lookups like "all students at UKH" or "all courses in
department D01" need to be O(1). We materialise them as **SETs** keyed by
`idx:<entity>:by_<column>:<value>`.

```
idx:student:by_university:UKH               -> {S001, S004, S012, ...}
idx:student:by_major:Computer Science       -> set of student ids
idx:course:by_department:D01                -> set of course ids
idx:course:by_university:UKH                -> *derived* index, see below
idx:hospital:by_city:Erbil                  -> set of hospital ids
idx:property:by_city:Erbil                  -> set of property ids
idx:property:by_status:for_sale             -> set of property ids
idx:event:by_organiser:AUK                  -> set of event ids
```

**Multi-condition queries** become **set intersections** &mdash; a single
`SINTER` returns the answer in microseconds:

```
SINTER idx:student:by_university:UKH idx:student:by_major:Computer\ Science
```

That intersection pattern is what the assignment's *multi-condition* and
*cross-domain* tasks need.

### Derived indexes

Courses link to a department (column `department`), and departments link
to a university. To answer *"all courses at UKH"* without a two-step
traversal at query time, the loader resolves each course's university
once at ingest and writes a derived index:

```
idx:course:by_university:<uni_id>
```

It also stores the resolved university name on the course hash itself so
the API responses are self-describing. This is a classic Redis trick:
**precompute at write time what you'll need to read in one shot.**

## 3. Numeric / range indexes (sorted sets)

GPAs, prices, ratings, beds, budgets, and dates are all queried by range
or top-N. We store them in **SORTED SETs** scored by the numeric value:

```
idx:student:by_gpa                  -> ZADD 3.85 S001
idx:student:by_age                  -> ZADD 22  S001
idx:property:by_listed_price_usd    -> ZADD 9193940 R043
idx:hospital:by_beds                -> ZADD 320 H001
idx:ministry:by_annual_budget_usd   -> ZADD 420000000 MOH
idx:reg:by_paid_usd                 -> ZADD 5.0 REG001
```

This gives us:
- `ZRANGEBYSCORE idx:student:by_gpa 3.5 4.0` for "GPA between 3.5 and 4.0"
- `ZREVRANGE idx:property:by_listed_price_usd 0 9` for top-10 most expensive
- O(log N) inserts/updates

## 4. Relationship indexes (sets, both directions)

Enrollments are a many-to-many join between students and courses. We
materialise both sides:

```
idx:enroll:students_in_course:<course_id>     -> set of student ids
idx:enroll:courses_of_student:<student_id>    -> set of course ids
```

Adjacency-style queries like *"give me students who took C101"* become a
single `SMEMBERS`. *"Did S001 take both C101 and C102?"* becomes one
`SINTER`. This is how we cheaply mimic Neo4j-style traversals without
leaving Redis. The same pattern is used for event registrations:

```
idx:reg:by_event:<event_id>     -> set of registration ids
```

We also store the grade for each (student, course) pair as its own hash
at `grade:<sid>:<cid>` so that "what grade did S001 get in C101?" is one
HGETALL with no scan.

## 5. Multi-value indexes (split-and-index)

Some columns hold comma-separated lists. The `specialities` column on
hospitals is the canonical example: `"General, Cardiology, Oncology"`. We
split it at load time and write one index entry per value:

```
idx:hospital:by_speciality:General      -> {H001, H012, ...}
idx:hospital:by_speciality:Cardiology   -> {H001, H034, ...}
idx:hospital:by_speciality:Oncology     -> {H001, ...}
```

Now *"hospitals with cardiology AND oncology"* is one `SINTER`.

## 6. Full-text search (RediSearch module)

For natural-language style queries &mdash; *"What courses does UKH offer?"*,
*"find a student named Layla"*, *"events at the Fair Ground"* &mdash; we
register three RediSearch indexes:

- **`idx_courses_ft`** indexes every `course:*` hash on `course_name`,
  `professor` (text), `department`, `mode`, `university` (tag), and
  `credits`, `max_cap` (numeric).
- **`idx_students_ft`** indexes `student:*` hashes on `full_name` (text),
  plus tag/numeric fields for filters.
- **`idx_events_ft`** indexes `event:*` hashes on `event_name`, `venue`
  (text), plus `type`, `city`, `organiser` (tag).

This unlocks query language like:

```
FT.SEARCH idx_courses_ft "@university:{UKH} @course_name:database"
FT.SEARCH idx_students_ft "@gpa:[3.5 4.0] @major:{Computer\\ Science}"
FT.SEARCH idx_events_ft "@organiser:{AUK} festival"
```

If the RediSearch module isn't loaded (you're on plain Redis instead of
Redis Stack), the loader skips index creation and the query layer falls
back to a `SCAN`-based substring filter.

## 7. Global membership sets

`all:student`, `all:course`, etc. give us a quick `SCARD` for counts and
`SRANDMEMBER` for sampling &mdash; handy for the dashboard.

## 8. Justification (why these choices for Redis)

| Requirement                    | Structure used         | Why                                              |
|--------------------------------|------------------------|--------------------------------------------------|
| Read a single record           | Hash + `HGETALL`       | Field-addressable, fast, compact                 |
| "Find all X with attribute Y"  | Set + `SMEMBERS`       | O(1) lookup, set algebra for combinations        |
| "Top N by score" / "between"   | Sorted Set + `ZRANGE`  | O(log N), built-in ranking                       |
| Many-to-many traversal         | Pair of sets per side  | Approximates a graph adjacency list              |
| Free-text / Q&A                | RediSearch index       | Inverted index, BM25 scoring, tag filtering      |
| Counts / membership            | `SCARD`, `SISMEMBER`   | O(1) — beats `COUNT(*)` on a relational DB       |
| Multi-value categorical        | Split-and-index        | One bool per value, intersect for AND queries    |

## 9. Memory ballpark

For the full 13,000 rows the database fits in well under 100 MB of RAM,
including all indexes. Loading takes about 6 seconds end-to-end on a
laptop, dominated by `csv.DictReader` rather than Redis itself.

## 10. How the web app uses this schema

The Flask app's `/dashboard` page is a direct visualisation of the
indexes described above &mdash; every chart caption shows the underlying
Redis command (`SCARD idx:property:by_city:*` for the city pie chart,
`ZCOUNT idx:student:by_gpa` for GPA buckets, and so on). The `/browse`
page reads the row hash directly via `HGETALL` and uses the sorted-set
indexes for the fast-path sort whenever the user clicks a numeric
column. This makes the schema legible even to someone who is not reading
the source code.
