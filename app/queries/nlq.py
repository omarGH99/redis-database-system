"""
nlq.py -- natural-language question answering (pattern matching over Redis).
"""

import re
from typing import Any, Dict, List

import redis

from . import core
from .core import _has_redisearch, _hydrate, _resolve_university
from .tasks import task_05_aggregation_avg_gpa_by_university


# ======================================================================
# BONUS: natural-language Q&A
# ======================================================================



# ======================================================================
# NATURAL-LANGUAGE QUERY  (rewritten — loose patterns + confidence)
# ======================================================================



# ======================================================================
# NATURAL-LANGUAGE QUERY  (expanded — 16 intents)
# ======================================================================

def natural_language_query(question: str) -> Dict[str, Any]:
    """
    Routes plain-English questions to the right Redis structures.
    Returns: intent, answer, explanation, confidence, matched_on.

    Supported intents:
      universities_by_course       "universities that offer database"
      courses_by_department        "list computer science courses"
      courses_by_university        "courses at UKH"
      courses_by_mode              "online courses" / "in-person courses"
      courses_by_professor         "who teaches Database Systems"
      students_by_major            "students in Data Science"
      students_by_university       "students at UKH"
      students_by_university_major "CS students at UKH"
      students_by_course           "who is enrolled in C101"
      students_by_semester         "students enrolled in Fall 2023"
      students_by_city             "students from Erbil"
      students_by_gpa              "students with GPA above 3.5"
      students_by_grade            "students who got an A in C101"
      courses_of_student           "what courses is S001 enrolled in"
      avg_gpa                      "average gpa at UKH"
      universities_by_city         "universities in Erbil"
      events_by_organiser          "events by AUK"
    """
    r = core.get_redis()
    raw = question.strip()
    q   = raw.lower()

    # ── helpers ───────────────────────────────────────────────────────
    def result(intent, answer, explanation, confidence=1.0, matched_on="", **kw):
        return {"intent": intent, "answer": answer, "explanation": explanation,
                "confidence": round(confidence, 2), "matched_on": matched_on, **kw}

    def _score(keywords):
        hits = sum(1 for k in keywords if k in q)
        return hits / len(keywords) if keywords else 0

    # Known values from the dataset (used for matching)
    SEMESTERS  = ["fall 2023", "spring 2024", "fall 2024", "spring 2025", "fall 2025"]
    SEM_PROPER = {"fall 2023": "Fall 2023", "spring 2024": "Spring 2024",
                  "fall 2024": "Fall 2024", "spring 2025": "Spring 2025",
                  "fall 2025": "Fall 2025"}
    CITIES     = ["erbil", "duhok", "sulaymaniyah", "halabja", "zakho"]
    CITY_PROPER = {"erbil": "Erbil", "duhok": "Duhok", "sulaymaniyah": "Sulaymaniyah",
                   "halabja": "Halabja", "zakho": "Zakho"}
    GRADES     = ["a+", "a", "a-", "b+", "b", "b-", "c+", "c", "c-", "d", "f"]
    GRADE_PROPER = {"a+":"A+","a":"A","a-":"A-","b+":"B+","b":"B","b-":"B-",
                    "c+":"C+","c":"C","c-":"C-","d":"D","f":"F"}

    dept_names = {k.split(":", 3)[-1].lower(): k.split(":", 3)[-1]
                  for k in r.scan_iter(match="idx:department:by_department_name:*", count=2000)}

    # ──────────────────────────────────────────────────────────────────
    # 1. COURSES OF A SPECIFIC STUDENT
    #    "what courses is S001 enrolled in" / "courses for student S001"
    # ──────────────────────────────────────────────────────────────────
    sid_match = re.search(r'\bS\d{3,4}\b', raw)
    if sid_match and any(w in q for w in ["course", "class", "enrolled", "taking", "study", "what"]):
        sid = sid_match.group(0)
        course_ids = sorted(r.smembers(f"idx:enroll:courses_of_student:{sid}"))
        student = r.hgetall(f"student:{sid}") or {}
        courses = _hydrate(r, course_ids, "course")
        return result(
            "courses_of_student",
            courses,
            f"SMEMBERS idx:enroll:courses_of_student:{sid} → {len(courses)} courses.",
            confidence=0.97, matched_on=f"student id {sid}",
            student_id=sid,
            student_name=student.get("full_name", sid),
        )

    # ──────────────────────────────────────────────────────────────────
    # 2. STUDENTS BY SEMESTER
    #    "students enrolled in Fall 2023" / "who studied in Spring 2024"
    # ──────────────────────────────────────────────────────────────────
    found_sem = next((s for s in SEMESTERS if s in q), None)
    if found_sem and any(w in q for w in ["student", "enrolled", "who", "studied", "took", "semester"]):
        sem_proper = SEM_PROPER[found_sem]
        enroll_ids = r.smembers(f"idx:enroll:by_semester:{sem_proper}")
        # Get student_ids from those enrollments
        pipe = r.pipeline()
        for eid in enroll_ids:
            pipe.hget(f"enrollment:{eid}", "student_id")
        sids = list(set(sid for sid in pipe.execute() if sid))
        students = _hydrate(r, sorted(sids), "student")
        return result(
            "students_by_semester",
            students,
            f"SMEMBERS idx:enroll:by_semester:{sem_proper} → {len(enroll_ids)} enrollments "
            f"→ {len(students)} unique students.",
            confidence=0.97, matched_on=f"semester '{sem_proper}'",
        )

    # ──────────────────────────────────────────────────────────────────
    # 3. STUDENTS BY GRADE IN A COURSE
    #    "students who got an A in C101" / "who passed C101 with B+"
    # ──────────────────────────────────────────────────────────────────
    found_grade = next((g for g in GRADES if re.search(rf'\b{re.escape(g)}\b', q)), None)
    cid_for_grade = re.search(r'\bC\d{2,4}\b', raw)
    if found_grade and cid_for_grade and any(w in q for w in ["got", "received", "grade", "passed", "scored", "student", "who"]):
        cid = cid_for_grade.group(0)
        grade_proper = GRADE_PROPER[found_grade]
        # Scan all students enrolled in that course and check their grade
        enrolled_sids = r.smembers(f"idx:enroll:students_in_course:{cid}")
        pipe = r.pipeline()
        for sid in enrolled_sids:
            pipe.hget(f"grade:{sid}:{cid}", "grade")
        grades = pipe.execute()
        matched_sids = [sid for sid, g in zip(enrolled_sids, grades) if g == grade_proper]
        students = _hydrate(r, sorted(matched_sids), "student")
        course_name = r.hget(f"course:{cid}", "course_name") or cid
        return result(
            "students_by_grade",
            students,
            f"Checked grade:{sid}:{cid} for all students in {cid} → "
            f"{len(matched_sids)} students got {grade_proper}.",
            confidence=0.95, matched_on=f"grade '{grade_proper}' in course {cid}",
            course_id=cid, course_name=course_name, grade=grade_proper,
        )

    # ──────────────────────────────────────────────────────────────────
    # 4. STUDENTS BY GPA RANGE
    #    "students with GPA above 3.5" / "students with gpa below 2.0"
    #    "top 10 students by gpa" / "highest gpa students"
    # ──────────────────────────────────────────────────────────────────
    if "gpa" in q and any(w in q for w in ["above", "over", "below", "under",
                                             "higher", "lower", "top", "highest",
                                             "more than", "less than", "between"]):
        num_match = re.search(r'\b(\d+\.?\d*)\b', q)
        num2_match = re.findall(r'\b(\d+\.?\d*)\b', q)

        if "top" in q and num_match:
            n = int(float(num_match.group(1)))
            ids = r.zrevrange("idx:student:by_gpa", 0, n - 1)
            students = _hydrate(r, list(ids), "student")
            return result(
                "students_by_gpa",
                students,
                f"ZREVRANGE idx:student:by_gpa 0 {n-1} → top {n} students by GPA.",
                confidence=0.95, matched_on="top N by gpa",
            )

        if "between" in q and len(num2_match) >= 2:
            lo, hi = float(num2_match[0]), float(num2_match[1])
            ids = r.zrangebyscore("idx:student:by_gpa", lo, hi)
            students = _hydrate(r, list(ids), "student")
            return result(
                "students_by_gpa",
                students,
                f"ZRANGEBYSCORE idx:student:by_gpa {lo} {hi} → {len(students)} students.",
                confidence=0.95, matched_on=f"gpa between {lo} and {hi}",
            )

        if any(w in q for w in ["above", "over", "higher", "more than"]) and num_match:
            threshold = float(num_match.group(1))
            ids = r.zrangebyscore("idx:student:by_gpa", threshold, 4.0)
            students = _hydrate(r, list(ids), "student")
            return result(
                "students_by_gpa",
                students,
                f"ZRANGEBYSCORE idx:student:by_gpa {threshold} 4.0 → {len(students)} students.",
                confidence=0.95, matched_on=f"gpa above {threshold}",
            )

        if any(w in q for w in ["below", "under", "lower", "less than"]) and num_match:
            threshold = float(num_match.group(1))
            ids = r.zrangebyscore("idx:student:by_gpa", 0, threshold)
            students = _hydrate(r, list(ids), "student")
            return result(
                "students_by_gpa",
                students,
                f"ZRANGEBYSCORE idx:student:by_gpa 0 {threshold} → {len(students)} students.",
                confidence=0.95, matched_on=f"gpa below {threshold}",
            )

    # ──────────────────────────────────────────────────────────────────
    # 5. STUDENTS BY CITY
    #    "students from Erbil" / "students in Duhok"
    # ──────────────────────────────────────────────────────────────────
    found_city = next((c for c in CITIES if c in q), None)
    if found_city and any(w in q for w in ["student", "students", "from", "who live", "living", "in"]):
        city_proper = CITY_PROPER[found_city]
        # Make sure it's not about universities
        if not any(w in q for w in ["universit", "courses", "course", "department"]):
            ids = sorted(r.smembers(f"idx:student:by_city:{city_proper}"))
            students = _hydrate(r, ids, "student")
            return result(
                "students_by_city",
                students,
                f"SMEMBERS idx:student:by_city:{city_proper} → {len(students)} students.",
                confidence=0.90, matched_on=f"city '{city_proper}'",
            )

    # ──────────────────────────────────────────────────────────────────
    # 6. UNIVERSITIES BY CITY
    #    "universities in Erbil" / "which universities are in Sulaymaniyah"
    # ──────────────────────────────────────────────────────────────────
    if found_city and any(w in q for w in ["universit", "college", "school"]):
        city_proper = CITY_PROPER[found_city]
        ids = sorted(r.smembers(f"idx:university:by_city:{city_proper}"))
        unis = _hydrate(r, ids, "university")
        return result(
            "universities_by_city",
            unis,
            f"SMEMBERS idx:university:by_city:{city_proper} → {len(unis)} universities.",
            confidence=0.92, matched_on=f"universities in {city_proper}",
        )

    # ──────────────────────────────────────────────────────────────────
    # 7. COURSES BY MODE
    #    "online courses" / "in-person courses" / "hybrid courses"
    # ──────────────────────────────────────────────────────────────────
    mode_map = {"online": "Online", "in-person": "In-person",
                "in person": "In-person", "hybrid": "Hybrid",
                "face to face": "In-person", "remote": "Online"}
    found_mode = next((m for m in mode_map if m in q), None)
    if found_mode and any(w in q for w in ["course", "courses", "class", "classes",
                                             "subjects", "taught", "offered", "available"]):
        mode_proper = mode_map[found_mode]
        ids = sorted(r.smembers(f"idx:course:by_mode:{mode_proper}"))
        courses = _hydrate(r, ids, "course")
        return result(
            "courses_by_mode",
            courses,
            f"SMEMBERS idx:course:by_mode:{mode_proper} → {len(courses)} courses.",
            confidence=0.93, matched_on=f"mode '{mode_proper}'",
        )

    # ──────────────────────────────────────────────────────────────────
    # 8. WHO TEACHES / COURSES BY PROFESSOR
    #    "who teaches Database Systems" / "courses by Dr. Khalid"
    # ──────────────────────────────────────────────────────────────────
    if any(w in q for w in ["who teaches", "who teach", "professor", "instructor",
                              "taught by", "courses by dr", "dr."]):
        # Try to find a course name in the question
        course_fragment = ""
        for kw in ["who teaches", "who teach", "taught by"]:
            if kw in q:
                course_fragment = q.split(kw, 1)[1].strip(" '\"?")
                break

        # Also check if they named a professor directly
        prof_match = re.search(r'dr\.?\s+\w+', q)

        if prof_match:
            # Search for professor by name fragment
            name_frag = prof_match.group(0).replace("dr.", "dr").strip().lower()
            matched_profs = []
            for key in r.scan_iter(match="idx:course:by_professor:*", count=2000):
                prof_name = key.split(":", 3)[-1]
                if name_frag.replace("dr ", "").strip() in prof_name.lower():
                    matched_profs.append((prof_name, key))

            if matched_profs:
                prof_name, key = matched_profs[0]
                ids = sorted(r.smembers(key))
                courses = _hydrate(r, ids, "course")
                return result(
                    "courses_by_professor",
                    courses,
                    f"SMEMBERS idx:course:by_professor:{prof_name} → {len(courses)} courses.",
                    confidence=0.90, matched_on=f"professor '{prof_name}'",
                    professor=prof_name,
                )

        if course_fragment:
            # Find what course they're asking about, then get its professor
            if _has_redisearch(r):
                from redis.commands.search.query import Query as FTQ
                try:
                    res = r.ft("idx_courses_ft").search(FTQ(course_fragment).paging(0, 3))
                    if res.docs:
                        cid = res.docs[0].id.split(":", 1)[1]
                        prof = r.hget(f"course:{cid}", "professor") or "unknown"
                        cname = r.hget(f"course:{cid}", "course_name") or cid
                        return result(
                            "courses_by_professor",
                            [{"course_id": cid, "course_name": cname, "professor": prof}],
                            f"FT.SEARCH found '{cname}' → professor is {prof}.",
                            confidence=0.88, matched_on=f"course name '{course_fragment}'",
                            professor=prof,
                        )
                except redis.ResponseError:
                    pass
            # Fallback scan
            for key in r.scan_iter(match="course:*", count=2000):
                name = (r.hget(key, "course_name") or "").lower()
                if course_fragment and course_fragment in name:
                    cid = key.split(":", 1)[1]
                    prof = r.hget(key, "professor") or "unknown"
                    cname = r.hget(key, "course_name") or cid
                    return result(
                        "courses_by_professor",
                        [{"course_id": cid, "course_name": cname, "professor": prof}],
                        f"Scanned course:* → found '{cname}' → professor is {prof}.",
                        confidence=0.80, matched_on=f"course name '{course_fragment}'",
                        professor=prof,
                    )

    # ──────────────────────────────────────────────────────────────────
    # 9. UNIVERSITIES BY COURSE KEYWORD
    # ──────────────────────────────────────────────────────────────────
    UNI_TRIGGERS = ["universities that offer", "universities offering",
                    "universities with", "which universities have",
                    "which universities offer", "universities that teach",
                    "universities that have", "unis that offer",
                    "schools that offer", "colleges that offer"]
    uni_trigger_hit = next((t for t in UNI_TRIGGERS if t in q), None)

    if uni_trigger_hit or ("universit" in q and any(
        kw in q for kw in ["offer", "have", "teach", "with", "that"]
    )):
        trigger = uni_trigger_hit or "universities + offer/have"
        subject = ""
        if uni_trigger_hit:
            subject = q.split(uni_trigger_hit, 1)[1].strip(" '\"?")
        else:
            for verb in ("offer", "teach", "have", "with"):
                if verb in q:
                    subject = q.split(verb, 1)[1].strip(" '\"?")
                    break
        if not subject:
            subject = q

        subject_words = [w for w in subject.split() if len(w) > 2]
        matched_uni_ids: set = set()
        matched_course_names: List[str] = []
        for key in r.scan_iter(match="course:*", count=2000):
            name_lower = (r.hget(key, "course_name") or "").lower()
            if any(w in name_lower for w in subject_words):
                uni = r.hget(key, "university") or ""
                if uni:
                    matched_uni_ids.add(uni)
                if len(matched_course_names) < 3:
                    matched_course_names.append(r.hget(key, "course_name") or "")

        if not matched_uni_ids:
            return result("unknown", [],
                f"No courses found with '{subject}' in the name.",
                confidence=0.4, matched_on=trigger)
        unis = _hydrate(r, sorted(matched_uni_ids), "university")
        return result(
            "universities_by_course", unis,
            f"Scanned course:* for '{subject}' → {len(matched_uni_ids)} universities. "
            f"Sample courses: {', '.join(matched_course_names[:3])}.",
            confidence=0.90, matched_on=trigger,
        )

    # ──────────────────────────────────────────────────────────────────
    # 10. COURSES BY DEPARTMENT NAME
    # ──────────────────────────────────────────────────────────────────
    found_dept_name = next(
        (proper for lower, proper in dept_names.items() if lower in q), None)
    COURSE_KWS = ["courses", "course", "classes", "class", "subjects",
                  "modules", "list", "show", "what", "give me"]
    course_kw_in_q = any(kw in q for kw in COURSE_KWS)
    student_in_q   = any(w in q for w in ["students", "student", "who", "enrolled", "took"])
    if found_dept_name and course_kw_in_q and not student_in_q:
        dept_ids = r.smembers(f"idx:department:by_department_name:{found_dept_name}")
        all_course_ids: List[str] = []
        for did in dept_ids:
            all_course_ids.extend(r.smembers(f"idx:course:by_department:{did}"))
        all_course_ids = sorted(set(all_course_ids))
        return result(
            "courses_by_department",
            _hydrate(r, all_course_ids, "course"),
            f"Found {len(dept_ids)} dept(s) named '{found_dept_name}' → "
            f"{len(all_course_ids)} courses.",
            confidence=0.95,
            matched_on=f"courses + department name '{found_dept_name}'",
        )

    # ──────────────────────────────────────────────────────────────────
    # 11. COURSES BY UNIVERSITY
    # ──────────────────────────────────────────────────────────────────
    COURSE_TRIGGERS = ["courses", "course", "classes", "class", "subjects",
                       "modules", "what is offered", "what does", "what do"]
    UNI_PREPOSITIONS = ["at", "by", "for", "offered by", "from", "in", "does", "do"]
    course_kw_hit = any(t in q for t in COURSE_TRIGGERS)
    uni_prep_hit  = any(p in q for p in UNI_PREPOSITIONS)

    if course_kw_hit or (uni_prep_hit and "university" in q):
        trigger = next((t for t in COURSE_TRIGGERS if t in q), "courses")
        uni_id = None
        for token in re.findall(r'[A-Za-z][A-Za-z0-9]*', raw):
            if r.exists(f"university:{token}"):
                uni_id = token; break
        if not uni_id:
            for code in ("UKH", "SPU", "UoS", "UZakho", "EBU"):
                if code.lower() in q:
                    uni_id = code; break
        if not uni_id:
            uni_id = _resolve_university(r, q)

        if uni_id:
            course_ids = sorted(r.smembers(f"idx:course:by_university:{uni_id}"))
            uni_meta   = r.hgetall(f"university:{uni_id}") if r.exists(f"university:{uni_id}") else {}
            return result(
                "courses_by_university",
                _hydrate(r, course_ids, "course"),
                f"SMEMBERS idx:course:by_university:{uni_id} → {len(course_ids)} courses.",
                confidence=0.90, matched_on=trigger,
                university_id=uni_id,
                university_name=uni_meta.get("name", uni_id),
            )

    # ──────────────────────────────────────────────────────────────────
    # 12. STUDENTS BY COURSE ENROLLMENT
    # ──────────────────────────────────────────────────────────────────
    ENROLL_TRIGGERS = ["enrolled in", "took", "taking", "who took", "who is in",
                       "in course", "for course", "registered for",
                       "signed up for", "who enrolled"]
    enroll_score = max(_score([t]) for t in ENROLL_TRIGGERS) if any(t in q for t in ENROLL_TRIGGERS) else 0
    cid_match = re.search(r'\bc(\d{2,4})\b', q)
    if cid_match and enroll_score == 0:
        enroll_score = 0.7
    course_name_words = {"database", "algorithm", "network", "security", "web",
                         "linear", "calculus", "statistics", "machine", "learning",
                         "systems", "programming", "engineering", "analysis", "lab",
                         "studio", "seminar", "practicum", "advanced", "fundamentals"}
    course_context = (bool(cid_match) or
                      any(w in q for w in ["course", "class", "module", "subject"]) or
                      any(w in q for w in course_name_words))
    if not course_context:
        enroll_score = 0

    if enroll_score >= 0.5:
        trigger = next((t for t in ENROLL_TRIGGERS if t in q), "course-id" if cid_match else "")
        fragment = ""
        for t in sorted(ENROLL_TRIGGERS, key=len, reverse=True):
            if t in q:
                fragment = q.split(t, 1)[1].strip(" '\"?")
                break
        if not fragment and cid_match:
            fragment = "C" + cid_match.group(1).upper()

        matched_courses: List[str] = []
        cid_direct = re.search(r'\bC\d{2,4}\b', raw)
        if cid_direct and r.exists(f"course:{cid_direct.group(0)}"):
            matched_courses = [cid_direct.group(0)]

        if not matched_courses and fragment:
            if _has_redisearch(r):
                from redis.commands.search.query import Query as FTQ
                try:
                    res = r.ft("idx_courses_ft").search(FTQ(fragment).paging(0, 5))
                    matched_courses = [d.id.split(":", 1)[1] for d in res.docs]
                except redis.ResponseError:
                    pass
            if not matched_courses:
                pat = fragment.lower()
                for key in r.scan_iter(match="course:*", count=2000):
                    name = (r.hget(key, "course_name") or "").lower()
                    if pat and pat in name:
                        matched_courses.append(key.split(":", 1)[1])
                        if len(matched_courses) >= 5:
                            break

        if not matched_courses:
            return result("unknown", [],
                f"No course matched '{fragment}'.", confidence=0.3, matched_on=trigger)

        keys = [f"idx:enroll:students_in_course:{c}" for c in matched_courses]
        sids = r.sunion(*keys) if len(keys) > 1 else r.smembers(keys[0])
        titles = [{"course_id": c,
                   "course_name": r.hget(f"course:{c}", "course_name")}
                  for c in matched_courses]
        return result(
            "students_by_course",
            _hydrate(r, sorted(sids), "student"),
            f"Resolved '{fragment}' to {len(matched_courses)} course(s) → "
            f"SMEMBERS idx:enroll:students_in_course sets.",
            confidence=enroll_score, matched_on=trigger,
            matched_courses=titles,
        )

    # ──────────────────────────────────────────────────────────────────
    # 13. STUDENTS BY MAJOR / UNIVERSITY
    # ──────────────────────────────────────────────────────────────────
    STUDENT_TRIGGERS = ["students", "show me students", "list students",
                        "list of students", "who are", "give me students",
                        "find students", "show students"]
    student_hit = any(t in q for t in STUDENT_TRIGGERS) or (
        any(w in q for w in ["students", "who", "list", "show", "find"]) and
        any(w in q for w in ["major", "university", "studying", "in", "at"])
    )
    if student_hit:
        trigger = next((t for t in STUDENT_TRIGGERS if t in q), "students")
        uni_id = None
        for code in ("UKH", "SPU", "UoS", "UZakho", "EBU"):
            if code.lower() in q:
                uni_id = code; break
        if not uni_id:
            for token in re.findall(r'[A-Za-z][A-Za-z0-9]*', raw):
                if r.exists(f"university:{token}"):
                    uni_id = token; break

        known_majors = {k.split(":", 3)[-1].lower(): k.split(":", 3)[-1]
                        for k in r.scan_iter(match="idx:student:by_major:*", count=2000)}
        found_major_lower = next((m for m in known_majors if m in q), None)
        found_major = known_majors[found_major_lower] if found_major_lower else None

        if uni_id and found_major:
            ids = sorted(r.sinter(f"idx:student:by_university:{uni_id}",
                                   f"idx:student:by_major:{found_major}"))
            return result("students_by_university_major",
                _hydrate(r, ids, "student"),
                f"SINTER by_university:{uni_id} × by_major:{found_major} → {len(ids)} students.",
                confidence=0.95, matched_on=f"{trigger} + {uni_id} + {found_major}")
        if uni_id:
            ids = sorted(r.smembers(f"idx:student:by_university:{uni_id}"))
            return result("students_by_university",
                _hydrate(r, ids, "student"),
                f"SMEMBERS idx:student:by_university:{uni_id} → {len(ids)} students.",
                confidence=0.85, matched_on=f"{trigger} + {uni_id}")
        if found_major:
            ids = sorted(r.smembers(f"idx:student:by_major:{found_major}"))
            return result("students_by_major",
                _hydrate(r, ids, "student"),
                f"SMEMBERS idx:student:by_major:{found_major} → {len(ids)} students.",
                confidence=0.85, matched_on=f"{trigger} + {found_major}")

    # ──────────────────────────────────────────────────────────────────
    # 14. AVERAGE GPA
    # ──────────────────────────────────────────────────────────────────
    if any(p in q for p in ["average gpa", "avg gpa", "mean gpa",
                              "gpa average", "what is the gpa", "gpa at"]):
        trigger = "average gpa"
        rows = task_05_aggregation_avg_gpa_by_university()
        for code in ("UKH", "SPU", "UoS", "UZakho", "EBU"):
            if code.lower() in q:
                match = next((r_ for r_ in rows if r_["university_id"] == code), None)
                if match:
                    return result("avg_gpa", match,
                        f"Averaged GPAs over {match['students']} students at {code}.",
                        confidence=0.95, matched_on=trigger)
        for token in re.findall(r'[A-Za-z][A-Za-z0-9]*', raw):
            if r.exists(f"university:{token}"):
                match = next((r_ for r_ in rows if r_["university_id"] == token), None)
                if match:
                    return result("avg_gpa", match,
                        f"Averaged GPAs at {token}.",
                        confidence=0.95, matched_on=trigger)
        return result("avg_gpa", rows[:15],
            "Averaged GPAs grouped by university (cohorts ≥ 1 student), sorted by size.",
            confidence=0.85, matched_on=trigger)

    # ──────────────────────────────────────────────────────────────────
    # 15. EVENTS BY ORGANISER
    # ──────────────────────────────────────────────────────────────────
    if any(w in q for w in ["event", "events", "conference", "workshop"]):
        for org in ("AUK", "UKH", "SPU", "UoS", "UZakho", "KRG", "Ministry"):
            if org.lower() in q:
                ids = sorted(r.smembers(f"idx:event:by_organiser:{org}"))
                if not ids:
                    for key in r.scan_iter(match="idx:event:by_organiser:*", count=2000):
                        if org.lower() in key.lower():
                            ids.extend(r.smembers(key))
                    ids = sorted(set(ids))
                return result("events_by_organiser",
                    _hydrate(r, ids, "event"),
                    f"SMEMBERS idx:event:by_organiser:{org} → {len(ids)} events.",
                    confidence=0.90, matched_on=f"events + {org}",
                    organiser=org,
                )

    # ──────────────────────────────────────────────────────────────────
    # 16. FREETEXT FALLTHROUGH via RediSearch
    # ──────────────────────────────────────────────────────────────────
    if _has_redisearch(r):
        from redis.commands.search.query import Query as FTQ
        for index_name, label in (
            ("idx_courses_ft",  "courses"),
            ("idx_students_ft", "students"),
            ("idx_events_ft",   "events"),
        ):
            try:
                res = r.ft(index_name).search(FTQ(q).paging(0, 10))
                if res.total:
                    docs = [{k: v for k, v in d.__dict__.items() if k != "payload"}
                            for d in res.docs]
                    return result(
                        f"freetext_{label}", docs,
                        f"No specific pattern matched — fell through to RediSearch "
                        f"on {index_name}. Found {res.total} result(s).",
                        confidence=0.4,
                        matched_on=f"freetext via {index_name}",
                    )
            except redis.ResponseError:
                pass

    # ──────────────────────────────────────────────────────────────────
    # UNKNOWN — with closest-match hint
    # ──────────────────────────────────────────────────────────────────
    checks = [
        ("students in a semester",          ["semester", "fall", "spring", "enrolled"]),
        ("students with GPA range",          ["gpa", "above", "below", "top"]),
        ("students from a city",             ["from", "city", "erbil", "duhok"]),
        ("students in a major/university",   ["students", "major", "university"]),
        ("courses at university",            ["courses", "classes", "offer"]),
        ("enrolled in course",               ["enrolled", "took", "in"]),
        ("universities in a city",           ["universities", "city"]),
        ("online/in-person courses",         ["online", "in-person", "mode"]),
        ("who teaches a course",             ["teaches", "professor", "instructor"]),
        ("events by organiser",              ["events", "conference"]),
        ("average gpa",                      ["gpa", "average", "avg"]),
    ]
    best, closest = 0.0, ""
    for label, kws in checks:
        s = sum(1 for k in kws if k in q) / len(kws)
        if s > best:
            best, closest = s, label

    hint = (f"Your question looks closest to '{closest}' ({int(best*100)}% match). "
            "Try adding more keywords from that pattern.") if best > 0.2 else \
           "No pattern matched. See the reference panel above for supported question shapes."

    return result("unknown", [], hint, confidence=best, matched_on=closest)
# ======================================================================
