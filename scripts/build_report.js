// build_report.js
const fs   = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, Header, Footer,
} = require('docx');

const FB = 'Georgia';
const FM = 'Courier New';

const bt = { style: BorderStyle.SINGLE, size: 4, color: 'BBBBBB' };
const ab = { top: bt, bottom: bt, left: bt, right: bt };

function p(text, opts = {}) {
  return new Paragraph({
    spacing: { after: opts.after ?? 140, before: opts.before ?? 0, line: 320 },
    children: [new TextRun({
      text, font: FB, size: 22,
      bold: opts.bold ?? false, italics: opts.italic ?? false,
    })],
  });
}

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    children: [new TextRun({ text, font: FB, size: 36, bold: true })],
  });
}

function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 260, after: 120 },
    children: [new TextRun({ text, font: FB, size: 26, bold: true })],
  });
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    spacing: { after: 80, line: 300 },
    children: [new TextRun({ text, font: FB, size: 22 })],
  });
}

function code(text) {
  return new Paragraph({
    spacing: { before: 60, after: 60, line: 260 },
    shading: { fill: 'F0EFEB', type: ShadingType.CLEAR },
    indent: { left: 360, right: 360 },
    children: [new TextRun({ text, font: FM, size: 18 })],
  });
}

function screenshotMarker(label) {
  return new Paragraph({
    spacing: { before: 200, after: 200 },
    shading: { fill: 'FFF3CD', type: ShadingType.CLEAR },
    indent: { left: 240, right: 240 },
    alignment: AlignmentType.CENTER,
    children: [new TextRun({
      text: `▸  SCREENSHOT: ${label}  ◂`,
      font: FM, size: 20, bold: true, color: 'B45309',
    })],
  });
}

function cell(text, opts = {}) {
  return new TableCell({
    borders: ab,
    width: { size: opts.width ?? 2000, type: WidthType.DXA },
    shading: { fill: opts.head ? 'E8E4D8' : 'FAF9F6', type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 140, right: 140 },
    children: [new Paragraph({
      children: [new TextRun({
        text, font: opts.mono ? FM : FB,
        size: opts.mono ? 18 : 20, bold: !!opts.head,
      })],
    })],
  });
}

function tbl(headers, rows, widths) {
  return new Table({
    width: { size: widths.reduce((a,b)=>a+b,0), type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((t,i) => cell(t, { head:true, width:widths[i] })),
      }),
      ...rows.map(r => new TableRow({
        children: r.map((t,i) => {
          const txt  = typeof t==='object' ? t.text : t;
          const mono = typeof t==='object' && t.mono;
          return cell(txt, { width:widths[i], mono });
        }),
      })),
    ],
  });
}

function spacer(pts = 160) {
  return new Paragraph({ spacing:{ before:pts, after:0 }, children:[] });
}

// ─── content ─────────────────────────────────────────────────────────────────
const C = [];

// Title
C.push(spacer(560));
C.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing:{ after:100 },
  children:[new TextRun({ text:'Redis Database System',
    font:FB, size:56, bold:true })],
}));
C.push(new Paragraph({
  alignment: AlignmentType.CENTER, spacing:{ after:80 },
  children:[new TextRun({ text:'A Key-Value Store as a Primary Database',
    font:FB, size:28, italics:true, color:'666666' })],
}));
C.push(spacer(200));
C.push(new Paragraph({
  alignment:AlignmentType.CENTER, spacing:{after:60},
  children:[new TextRun({ text:'Advanced Database Systems  ·  Spring 2026',
    font:FB, size:22, color:'444444' })],
}));
C.push(new Paragraph({
  alignment:AlignmentType.CENTER, spacing:{after:60},
  children:[new TextRun({ text:'Dr. Shamal Taha',
    font:FB, size:22, color:'444444' })],
}));
C.push(new Paragraph({
  alignment:AlignmentType.CENTER, spacing:{after:60},
  children:[new TextRun({ text:'American University of Kurdistan',
    font:FB, size:22, color:'444444' })],
}));
C.push(spacer(100));
C.push(new Paragraph({
  alignment:AlignmentType.CENTER, spacing:{after:0},
  children:[new TextRun({ text:'By:  Omar  ·  Aya  ·  Shelan',
    font:FB, size:24, bold:true })],
}));

// ── 1. Introduction ───────────────────────────────────────────────────────────
C.push(spacer(360));
C.push(h1('1. Introduction'));
C.push(p(
  'Redis is almost always described as a cache. This project argues against that ' +
  'framing. With the right naming convention and the right data structure for each ' +
  'access pattern, Redis can serve as the primary store for a multi-domain relational ' +
  'dataset and answer the full range of queries a university application needs — ' +
  'filtering, sorting, aggregation, full-text search, and cross-table joins — in ' +
  'sub-millisecond time.'
));
C.push(p(
  'The project was built for the Advanced Database Systems course at the American ' +
  'University of Kurdistan. We were given thirteen CSV files (one thousand rows each) ' +
  'covering universities, departments, courses, students, enrollments, hospitals, ' +
  'companies, properties, government ministries and events. We chose Redis, loaded ' +
  'all thirteen tables, designed a schema that maps each table to the most appropriate ' +
  'Redis data structure, and built a Flask web application around it.'
));
C.push(p(
  'The centrepiece of the application is the natural-language query interface, ' +
  'which lets a user type a plain-English question and receive a full result set ' +
  'with an explanation of exactly which Redis command answered it. The rest of the ' +
  'application — a live dashboard, a table browser, and the ten required task queries ' +
  '— supports and demonstrates the same underlying schema.'
));

// ── 2. Setup ──────────────────────────────────────────────────────────────────
C.push(h1('2. Environment and Setup'));
C.push(p(
  'The entire stack runs from a single Docker Compose file. Redis Stack — the ' +
  'official distribution that includes the RediSearch module — runs in one container ' +
  'on port 6379. The application layer is a Python Flask server using the redis-py ' +
  'client library. Getting from a fresh machine to a running application takes three ' +
  'commands:'
));
C.push(code('docker compose up -d'));
C.push(code('python scripts/load_redis.py --reset'));
C.push(code('python app/app.py'));
C.push(p(
  'The loader (scripts/load_redis.py) reads each CSV, creates one Redis Hash per ' +
  'row, and builds all the reverse indexes described in Section 4. It finishes in ' +
  'roughly six seconds for thirteen thousand rows. The project structure is as follows:'
));
C.push(code('redis_project/'));
C.push(code('  docker-compose.yml       Redis Stack container definition'));
C.push(code('  scripts/load_redis.py    CSV ingestion and index creation'));
C.push(code('  app/queries.py           All query logic: tasks, NL routing, browse'));
C.push(code('  app/app.py               Flask routes and JSON endpoints'));
C.push(code('  templates/               Jinja HTML for all four pages'));
C.push(code('  static/vendor/           Chart.js bundled for offline use'));
C.push(code('  data/                    The 13 CSV files'));

// ── 3. Dataset ────────────────────────────────────────────────────────────────
C.push(h1('3. Dataset'));
C.push(p(
  'The dataset spans nine domains across thirteen files. We focused the web ' +
  'application on the six student-facing tables, which contain the richest ' +
  'relationships and produce the most meaningful queries. The remaining seven ' +
  'tables (hospitals, companies, properties, ministries, projects, patients, ' +
  'registrations) are loaded into Redis and used by the task queries, but are ' +
  'not exposed in the browser or the natural-language interface.'
));
C.push(tbl(
  ['Table', 'Rows', 'Key content'],
  [
    ['universities',     '1,000', 'Five real KRI universities (UKH, SPU, UoS, UZakho, EBU) plus 995 synthetic ones.'],
    ['departments',      '1,000', 'Linked to universities. Ten named department types: Computer Science, Data Science, Cybersecurity, etc.'],
    ['courses',          '1,000', 'Linked to departments by dept_id. University resolved at load time.'],
    ['students',         '1,000', 'Linked to a university. Has major, GPA (float), city, enroll year.'],
    ['enrollments',      '1,000', 'Many-to-many between students and courses, with grade and semester.'],
    ['events',           '1,000', 'Cultural, academic and government events. Linked by organiser name.'],
  ],
  [1600, 900, 5960],
));

// ── 4. Schema Design ──────────────────────────────────────────────────────────
C.push(h1('4. Schema Design'));
C.push(p(
  'A Redis schema is a naming convention plus a deliberate choice of data structure ' +
  'for each access pattern. We used four building blocks, chosen based on how the ' +
  'data would be read, not how it looks in a relational table.'
));

C.push(h2('4.1  Hashes — storing the row'));
C.push(p(
  'Each CSV row becomes a Redis Hash at a typed key: <entity>:<id>. For example, ' +
  'student:S001 or course:C101. Hash fields map directly to CSV columns. Because ' +
  'fields are independently addressable with HGET, a single-field read never ' +
  'touches the rest of the row, and field-level updates are atomic. The full ' +
  'mapping for each table is in the loaders in scripts/load_redis.py.'
));
C.push(code('HGETALL student:S001'));
C.push(code('  → { student_id:S001, full_name:Layla Aziz Hassan, age:22,'));
C.push(code('      city:Erbil, university:UKH, major:Computer Science,'));
C.push(code('      gpa:3.85, enroll_year:2022, phone:+964-750-111-0001 }'));

C.push(h2('4.2  Sets — categorical reverse indexes'));
C.push(p(
  'Every column that will be filtered on gets a reverse index as a Set. The key ' +
  'name encodes the table, column and value:'
));
C.push(code('idx:student:by_university:UKH          → { S001, S004, S012, … }'));
C.push(code('idx:student:by_major:Computer Science  → { S001, S008, S015, … }'));
C.push(code('idx:course:by_university:UKH           → { C039, C142, C388, … }'));
C.push(p(
  'A multi-condition filter becomes a single SINTER. Finding Computer Science ' +
  'students at UKH is one command with a response time under a millisecond:'
));
C.push(code('SINTER idx:student:by_university:UKH  idx:student:by_major:Computer\\ Science'));

C.push(h2('4.3  Sorted Sets — numeric and range indexes'));
C.push(p(
  'Columns queried by range or by ranking (GPA, age, ticket count) are stored in ' +
  'Sorted Sets scored by the numeric value:'
));
C.push(code('idx:student:by_gpa  →  3.85 → S001,  3.20 → S002,  3.90 → S003, …'));
C.push(p(
  'ZRANGEBYSCORE handles range queries ("GPA between 3.5 and 4.0") and ZREVRANGE ' +
  'handles top-N rankings, both in O(log n). The Browse page detects a sorted-set ' +
  'index automatically and labels it engine=zset in the status line.'
));

C.push(h2('4.4  Many-to-many sets'));
C.push(p(
  'Enrollments are materialised on both sides of the relationship:'
));
C.push(code('idx:enroll:students_in_course:C101  → { S003, S019, S042, … }'));
C.push(code('idx:enroll:courses_of_student:S001  → { C101, C203, C388, … }'));
C.push(p(
  '"Which students took C101?" is a single SMEMBERS. This mirrors a graph ' +
  'adjacency list and gives constant-time traversal in both directions without ' +
  'a dedicated graph engine. The natural-language query interface uses these ' +
  'indexes directly to answer questions like "who is enrolled in Database Systems".'
));

C.push(h2('4.5  Derived index and RediSearch'));
C.push(p(
  'Because courses link to departments rather than directly to universities, the ' +
  'loader resolves each course\'s university at ingest and writes a derived index ' +
  'idx:course:by_university:<uni>. This is the standard Redis pattern: compute at ' +
  'write time what you will need to read in one shot.'
));
C.push(p(
  'Three RediSearch full-text indexes are also built at load time over the Hash ' +
  'prefixes course:*, student:* and event:* (see build_search_indexes() in ' +
  'scripts/load_redis.py). They add BM25-ranked free-text search and tag filters ' +
  'on top of the core schema, and they are what powers the natural-language ' +
  'interface when a user types a course name rather than a course ID.'
));

// ── 5. Natural-Language Query Interface ───────────────────────────────────────
C.push(h1('5. Natural-Language Query Interface'));
C.push(p(
  'The Query page is the centrepiece of the application. A user types a plain-English ' +
  'question into a text box and receives a full result set displayed as a table, ' +
  'together with an intent label, a confidence score, and a one-line explanation of ' +
  'exactly which Redis command was used to produce the answer. There is no language ' +
  'model involved — the routing is deterministic pattern matching, which makes it ' +
  'fast, transparent, and easy to defend.'
));
C.push(screenshotMarker('Query page — "universities that offer database" returning 44 results with intent label, confidence 90%, and explanation'));

C.push(h2('5.1  How routing works'));
C.push(p(
  'The function natural_language_query() in app/queries.py receives the raw question ' +
  'string. It runs a sequence of pattern checks, each of which tries to detect a ' +
  'specific intent by looking for trigger words and extracting entities. The first ' +
  'check to succeed routes to its Redis path; if none match, the function falls back ' +
  'to a RediSearch full-text search across courses, students and events in turn. ' +
  'If that also returns nothing, the page shows a "No match found" panel listing all ' +
  'supported patterns rather than a vague error.'
));
C.push(p(
  'Every response object carries four fields beyond the result rows: intent (a short ' +
  'machine-readable label), explanation (a human-readable description of the Redis ' +
  'command used), confidence (a 0–1 score based on how many trigger keywords matched), ' +
  'and matched_on (the exact keywords that fired the routing decision).'
));

C.push(h2('5.2  Supported intents'));
C.push(tbl(
  ['Intent', 'Trigger phrases', 'Redis path'],
  [
    ['universities_by_course',
     '"universities that offer X", "universities offering X", "which universities have X"',
     'Scans course:* names for keyword X → collects distinct university IDs → HGETALL university:*'],
    ['courses_by_department',
     '"list <dept> courses", "show me <dept> classes", "what are the <dept> courses"',
     'SMEMBERS idx:department:by_department_name:<dept> → SMEMBERS idx:course:by_department:<id> (union)'],
    ['courses_by_university',
     '"courses at <uni>", "classes offered by <uni>", "what does <uni> offer"',
     'SMEMBERS idx:course:by_university:<uni>'],
    ['students_by_major',
     '"show me students in <major>", "list students studying <major>"',
     'SMEMBERS idx:student:by_major:<major>'],
    ['students_by_university_major',
     '"students at <uni> in <major>"',
     'SINTER idx:student:by_university:<uni>  idx:student:by_major:<major>'],
    ['students_by_course',
     '"who is enrolled in C101", "students who took Database Systems"',
     'FT.SEARCH idx_courses_ft for course name → SMEMBERS idx:enroll:students_in_course:<id>'],
    ['avg_gpa',
     '"average gpa at <uni>", "avg gpa"',
     'ZSCORE fan-out over idx:student:by_gpa per university, client-side average'],
    ['top_properties',
     '"top N properties", "most expensive properties in <city>"',
     'ZREVRANGE idx:property:by_listed_price_usd, optionally intersected with by_city Set'],
    ['events_by_organiser',
     '"events by AUK", "events organised by KRG"',
     'SMEMBERS idx:event:by_organiser:<organiser>'],
  ],
  [1800, 2400, 4260],
));

C.push(spacer(80));
C.push(p(
  'The intent priority order matters. The universities_by_course check is placed ' +
  'before courses_by_university so that "universities that offer database" routes ' +
  'correctly to universities and not to courses. The students_by_course check ' +
  'requires course-name context words (such as "database", "network", "algorithm") ' +
  'before it fires, to avoid stealing questions like "show me students in Computer ' +
  'Science" which should route to students_by_major instead.'
));

C.push(h2('5.3  Example questions and answers'));
C.push(tbl(
  ['Question typed by user', 'Intent matched', 'Result'],
  [
    ['"universities that offer database"',
     'universities_by_course', '44 universities with Database Systems courses'],
    ['"list computer science courses"',
     'courses_by_department', '100 courses across all CS departments'],
    ['"courses at UKH"',
     'courses_by_university', '11 courses offered at UKH'],
    ['"show me students in Data Science"',
     'students_by_major', '110 students in the Data Science major'],
    ['"who is enrolled in C101"',
     'students_by_course', '7 students enrolled in course C101'],
    ['"students who took Database Systems"',
     'students_by_course', 'Resolved course name via RediSearch, returned 9 students'],
    ['"average gpa at UKH"',
     'avg_gpa', 'avg 3.525, min 2.65, max 3.97, over 10 students'],
    ['"events by AUK"',
     'events_by_organiser', '72 events organised by AUK'],
  ],
  [2400, 1900, 4160],
));
C.push(screenshotMarker('Query page — "list computer science courses" showing 100 results with COURSES_BY_DEPARTMENT intent, teal badge, 95% confidence'));
C.push(screenshotMarker('Query page — "who is enrolled in C101" showing 7 students with matched_on: enrolled in + course-id'));

// ── 6. The 10 Tasks ───────────────────────────────────────────────────────────
C.push(h1('6. The 10 Required Tasks'));
C.push(p(
  'The ten tasks are implemented as individual Python functions in app/queries.py ' +
  'and exposed as JSON endpoints in app/app.py. They are accessible from the Tasks ' +
  'page, which mirrors the Browse layout: the six table chips show live row counts, ' +
  'a query bar lets the user run or modify any task, and results appear as a raw ' +
  'JSON output box followed by a formatted table. The full implementations are in ' +
  'app/queries.py; only the key Redis commands are listed here.'
));
C.push(tbl(
  ['#', 'Tier', 'Task', 'Redis commands'],
  [
    ['1',  'Basic',        'Load and count all rows',              {text:'SCARD all:*', mono:true}],
    ['2',  'Basic',        'Filter students by university + major',{text:'SINTER (two reverse-index Sets)', mono:true}],
    ['3',  'Basic',        'Top-N most expensive properties',      {text:'ZREVRANGE idx:property:by_listed_price_usd', mono:true}],
    ['4',  'Intermediate', 'CRUD on a student',                    {text:'HSET / HGETALL / DEL inside a pipeline', mono:true}],
    ['5',  'Intermediate', 'Average GPA by university',            {text:'ZSCORE fan-out, Python group-by', mono:true}],
    ['6',  'Intermediate', 'Multi-condition: uni × major × GPA',   {text:'SINTER + ZSCORE range filter', mono:true}],
    ['7',  'Intermediate', 'Students × universities × departments',{text:'HGETALL across three Hash prefixes', mono:true}],
    ['8',  'Advanced',     'Full-text search on courses',          {text:'FT.SEARCH idx_courses_ft', mono:true}],
    ['9',  'Advanced',     'Referential integrity check',          {text:'EXISTS across six relations — returned 0 orphans', mono:true}],
    ['10', 'Advanced',     'Composite dashboard query',            {text:'SCARD + ZREVRANGE + SINTER in one call', mono:true}],
  ],
  [360, 1200, 2700, 4200],
));
C.push(spacer(80));
C.push(p(
  'Task 4 (CRUD) wraps all Hash updates and Set index changes in a Redis pipeline ' +
  'so they complete in a single round trip and stay consistent. Task 8 (RediSearch) ' +
  'also has a SCAN-based fallback so it works on plain Redis without the module. ' +
  'Task 9 (validation) confirmed zero orphan foreign keys across 1,000 enrollments, ' +
  '1,000 courses and 1,000 students.'
));

// ── 7. Dashboard and Browser ──────────────────────────────────────────────────
C.push(h1('7. Dashboard and Table Browser'));

C.push(h2('Dashboard'));
C.push(p(
  'Eight live Chart.js charts, each labelled with the Redis command that produced ' +
  'it. Chart.js is bundled locally in static/vendor/ so the page works without ' +
  'internet access. Charts cover: rows per table, students per university and major, ' +
  'GPA distribution, enrollments per semester, courses per department, events per ' +
  'type, and events per city. All data comes from SCARD and ZCOUNT over the reverse ' +
  'indexes — no row scans.'
));
C.push(screenshotMarker('Dashboard — 8 live charts showing students per university, GPA distribution, etc.'));

C.push(h2('Browse Tables'));
C.push(p(
  'A database-explorer page exposing the six student-facing tables. Clicking a ' +
  'column header sorts the table; the page detects whether a sorted-set index ' +
  'exists and uses it (engine=zset) or falls back to a Python sort ' +
  '(engine=scan-and-sort). A free-text search box filters all fields. Pagination ' +
  'at 25 / 50 / 100 / 250 rows per page.'
));

// ── 8. Why Redis ──────────────────────────────────────────────────────────────
C.push(h1('8. Why Redis for This Dataset'));
C.push(p(
  'The five options in the assignment were MongoDB, Cassandra, Redis, Neo4j and ' +
  'ChromaDB. Redis was the right choice for this workload for three reasons.'
));
C.push(p(
  'First, the most common university queries are categorical filters combined with ' +
  'optional numeric ranges: students at this university in this major with this ' +
  'GPA. These map perfectly onto SINTER (for the categorical part) and ZRANGEBYSCORE ' +
  '(for the numeric part). In Redis these are native primitives. In every other ' +
  'option on the list they require a query planner, an index scan, or both.'
));
C.push(p(
  'Second, the many-to-many enrollment relationship — which student took which course ' +
  '— is the foundation of the natural-language query interface. Materialising it as ' +
  'two Sets (students per course, courses per student) gives constant-time lookup ' +
  'in both directions. This is the same adjacency-list pattern a graph database ' +
  'would use, implemented in a few Set keys.'
));
C.push(p(
  'Third, the RediSearch module turns the same Hash objects that store the rows into ' +
  'full-text search documents at no extra storage cost. This is what enables the ' +
  'natural-language interface to resolve "Database Systems" to a course ID rather ' +
  'than requiring the user to know the exact ID. No other option on the list gives ' +
  'both sub-millisecond key lookups and BM25 full-text in a single engine.'
));
C.push(tbl(
  ['Requirement', 'Redis approach', 'Why it fits'],
  [
    ['Categorical filter',   'SINTER',               'O(1) membership, no index scan'],
    ['Numeric range / top-N','ZRANGEBYSCORE / ZREVRANGE', 'O(log n) — no full-table scan'],
    ['Many-to-many join',    'Pair of reverse Sets',  'Both sides materialised at write, O(1) lookup'],
    ['Free-text matching',   'FT.SEARCH (RediSearch)','BM25 ranking, tag + numeric filters'],
    ['Cross-entity join',    'HGETALL on multiple prefixes', 'Hash lookup is O(1) per key'],
  ],
  [1900, 2600, 4060],
));

// ── 9. Limitations ────────────────────────────────────────────────────────────
C.push(h1('9. Limitations and Future Work'));
C.push(p(
  'Client-side aggregation is the main limitation. Task 5 (average GPA by university) ' +
  'fans out one ZSCORE call per student per university group and averages in Python. ' +
  'At one thousand students this is fast; at ten million it would need precomputed ' +
  'counters or an analytical offload layer.'
));
C.push(p(
  'The natural-language routing is deterministic pattern matching. It handles the ' +
  'seven intents we defined well, but any phrasing that falls outside those patterns ' +
  'reaches the fallback or returns no results. The natural next step would be to ' +
  'replace the routing layer with a small language model that emits Redis commands ' +
  'directly, which would handle arbitrary questions without explicit patterns.'
));
C.push(p(
  'Adding a Redis HNSW vector-search index over course description embeddings would ' +
  'enable semantic search ("find courses similar to machine learning") and close the ' +
  'gap with the ChromaDB option in the assignment.'
));

// ── 10. Conclusion ────────────────────────────────────────────────────────────
C.push(h1('10. Conclusion'));
C.push(p(
  'This project demonstrates that Redis, with a schema built around Sets, Sorted ' +
  'Sets and the RediSearch module, can serve as the primary database for a ' +
  'multi-domain relational dataset and support the full range of queries a ' +
  'university application needs.'
));
C.push(p(
  'The natural-language query interface is the clearest demonstration of this. ' +
  'When a user types "universities that offer database", the system resolves the ' +
  'question to 44 universities by scanning course names, collecting university IDs, ' +
  'and hydrating their Hash records — all using the indexes built at load time, with ' +
  'no query planner involved. When a user types "who is enrolled in C101", the ' +
  'system does one SMEMBERS on a pre-built Set and returns the answer instantly. ' +
  'The schema made these questions answerable; Redis made them fast.'
));
C.push(p(
  'Every one of the ten required tasks returns correct results. The referential ' +
  'integrity check found zero orphans across all 1,000 enrolled records. The ' +
  'dashboard, table browser, task runner and query interface all run from a single ' +
  'Docker container on a laptop, with no infrastructure beyond Docker Desktop and ' +
  'a Python environment.'
));

// ─── document ─────────────────────────────────────────────────────────────────
const doc = new Document({
  creator: 'Omar, Aya, Shelan',
  title: 'Redis Database System — Advanced Database Systems',
  numbering: {
    config: [{
      reference: 'bullets',
      levels: [{
        level:0, format:LevelFormat.BULLET, text:'–',
        alignment:AlignmentType.LEFT,
        style:{ paragraph:{ indent:{ left:540, hanging:300 } } },
      }],
    }],
  },
  styles: {
    default: { document: { run:{ font:FB, size:22 } } },
    paragraphStyles: [
      { id:'Heading1', name:'Heading 1', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ size:36, bold:true, font:FB },
        paragraph:{ spacing:{ before:360, after:160 }, outlineLevel:0 } },
      { id:'Heading2', name:'Heading 2', basedOn:'Normal', next:'Normal', quickFormat:true,
        run:{ size:26, bold:true, font:FB },
        paragraph:{ spacing:{ before:260, after:120 }, outlineLevel:1 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size:{ width:12240, height:15840 },
        margin:{ top:1440, right:1440, bottom:1440, left:1440 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment:AlignmentType.RIGHT,
          children:[new TextRun({
            text:'Redis Database System  ·  Advanced Database Systems  ·  Spring 2026',
            font:FB, size:18, italics:true, color:'999999',
          })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment:AlignmentType.CENTER,
          children:[
            new TextRun({ text:'By: Omar, Aya, Shelan  ·  Page ',
              font:FB, size:18, color:'999999' }),
            new TextRun({ children:[PageNumber.CURRENT],
              font:FB, size:18, color:'999999' }),
          ],
        })],
      }),
    },
    children: C,
  }],
});

const out = path.resolve(__dirname, '..', 'docs', 'Report.docx');
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(out, buf);
  console.log('wrote', out, '—', Math.round(buf.length/1024)+'KB');
}).catch(e => { console.error(e); process.exit(1); });
