"""Library of B2-exam-style writing tasks (IELTS General/Academic and Cambridge B2 First).

Prompts are in English, like the real exams. `points` are the content points the answer
must cover; task achievement is judged against them.
"""

from __future__ import annotations

EXAMS: dict[str, str] = {
    "ielts_gt_task1": "IELTS General · Task 1 (letter)",
    "ielts_task2": "IELTS · Task 2 (essay)",
    "b2_first_essay": "B2 First · Part 1 (essay)",
    "b2_first_part2": "B2 First · Part 2",
    "work": "Workplace",
}

GENRES: dict[str, str] = {
    "email_formal": "Formal email / letter",
    "email_informal": "Informal email / letter",
    "email_semi": "Semi-formal email / letter",
    "opinion_essay": "Opinion essay",
    "discussion_essay": "Discussion essay",
    "report": "Report",
    "review": "Review",
    "article": "Article",
    "summary": "Summary",
}

TASKS: list[dict] = [
    {
        "id": "work-apply-position",
        "exam": "work", "genre": "email_formal", "register": "formal",
        "title": "Apply for a job",
        "prompt": ("You have seen an online advertisement for a Customer Support Specialist at an international "
                   "software company. Write an email to the hiring manager applying for the position."),
        "points": ["say which position you are applying for and where you saw it",
                   "describe your relevant experience and skills",
                   "explain why you want to work for this company",
                   "say when you are available for an interview"],
        "words": [150, 220], "minutes": 25,
    },
    {
        "id": "work-delay-colleague",
        "exam": "work", "genre": "email_semi", "register": "neutral",
        "title": "A project is delayed",
        "prompt": ("A project you are working on will not be finished on time. Write an email to your manager "
                   "to explain the situation."),
        "points": ["explain what has caused the delay", "say what you have already done to solve it",
                   "propose a new deadline and a plan"],
        "words": [120, 180], "minutes": 20,
    },
    {
        "id": "work-thank-colleague",
        "exam": "work", "genre": "email_informal", "register": "informal",
        "title": "Thank a colleague who is leaving",
        "prompt": ("A colleague who helped you a lot in your first months at work is moving to another company. "
                   "Write an email to say goodbye."),
        "points": ["thank them for a specific way they helped you", "say what you will miss",
                   "suggest how you can stay in touch"],
        "words": [100, 160], "minutes": 15,
    },
    {
        "id": "work-meeting-summary",
        "exam": "work", "genre": "summary", "register": "neutral",
        "title": "Summarise a team meeting",
        "prompt": ("Your team met to discuss moving from office work to a hybrid model (three days at home, two in "
                   "the office). Write a short summary for colleagues who missed the meeting."),
        "points": ["the main advantages that were mentioned", "the main concerns", "what was decided and the next steps"],
        "words": [120, 180], "minutes": 20,
    },
    {
        "id": "ielts-gt1-complaint",
        "exam": "ielts_gt_task1", "genre": "email_formal", "register": "formal",
        "title": "Complain about a training course",
        "prompt": ("You recently attended a paid online training course for your job, but you were not satisfied "
                   "with it. Write a letter to the training company. In your letter:"),
        "points": ["give details of the course you attended", "explain what the problems were",
                   "say what you would like the company to do"],
        "words": [150, 200], "minutes": 20,
    },
    {
        "id": "ielts-gt1-friend-visit",
        "exam": "ielts_gt_task1", "genre": "email_informal", "register": "informal",
        "title": "Invite a friend to visit",
        "prompt": ("A friend from another country is planning to visit your city for a week. Write a letter to "
                   "your friend. In your letter:"),
        "points": ["say how you feel about the visit", "suggest some places to visit and things to do",
                   "give advice about what to bring"],
        "words": [150, 200], "minutes": 20,
    },
    {
        "id": "ielts-gt1-manager-time-off",
        "exam": "ielts_gt_task1", "genre": "email_semi", "register": "semi-formal",
        "title": "Ask your manager for time off",
        "prompt": "You would like to take some time off work to study for an exam. Write a letter to your manager. In your letter:",
        "points": ["explain why you need time off", "say how long you need and when",
                   "explain how your work will be covered while you are away"],
        "words": [150, 200], "minutes": 20,
    },
    {
        "id": "ielts-t2-remote-work",
        "exam": "ielts_task2", "genre": "opinion_essay", "register": "formal",
        "title": "Working from home",
        "prompt": ("More and more people are working from home instead of going to an office. Do the advantages "
                   "of this trend outweigh the disadvantages?"),
        "points": ["give your opinion clearly", "discuss advantages and disadvantages with examples",
                   "write a clear conclusion"],
        "words": [250, 320], "minutes": 40,
    },
    {
        "id": "ielts-t2-university-jobs",
        "exam": "ielts_task2", "genre": "discussion_essay", "register": "formal",
        "title": "University or practical skills?",
        "prompt": ("Some people think universities should prepare students for jobs, while others believe they "
                   "should focus on knowledge for its own sake. Discuss both views and give your own opinion."),
        "points": ["discuss the first view", "discuss the second view", "give and justify your own opinion"],
        "words": [250, 320], "minutes": 40,
    },
    {
        "id": "ielts-t2-english-careers",
        "exam": "ielts_task2", "genre": "opinion_essay", "register": "formal",
        "title": "English and career success",
        "prompt": ("In many countries, speaking English is now considered essential for a successful career. "
                   "To what extent do you agree or disagree?"),
        "points": ["state how far you agree", "support your position with reasons and examples",
                   "consider the opposite view", "write a clear conclusion"],
        "words": [250, 320], "minutes": 40,
    },
    {
        "id": "b2-essay-technology",
        "exam": "b2_first_essay", "genre": "opinion_essay", "register": "neutral",
        "title": "Technology and young people",
        "prompt": ("In your English class you have been talking about technology. Now your teacher has asked you "
                   "to write an essay. “Has technology made young people's lives better?”"),
        "points": ["communication with friends and family", "education and work",
                   "your own idea"],
        "words": [140, 190], "minutes": 40,
    },
    {
        "id": "b2-essay-cities",
        "exam": "b2_first_essay", "genre": "opinion_essay", "register": "neutral",
        "title": "Living in a big city",
        "prompt": ("In your English class you have been talking about where people live. Now your teacher has "
                   "asked you to write an essay. “Is it better to live in a big city than in a small town?”"),
        "points": ["job opportunities", "cost of living", "your own idea"],
        "words": [140, 190], "minutes": 40,
    },
    {
        "id": "b2-review-app",
        "exam": "b2_first_part2", "genre": "review", "register": "neutral",
        "title": "Review a learning app",
        "prompt": ("You see this notice on an English-learning website: “Reviews wanted! Tell us about an app or "
                   "website that helped you learn something. What did you learn? What was good and bad about it? "
                   "Would you recommend it?” Write your review."),
        "points": ["what you learned with it", "what was good and what was bad", "whether you recommend it and to whom"],
        "words": [140, 190], "minutes": 40,
    },
    {
        "id": "b2-report-workplace",
        "exam": "b2_first_part2", "genre": "report", "register": "formal",
        "title": "Report: improving the office",
        "prompt": ("Your manager has asked you to write a report about the facilities at your workplace. Describe "
                   "what works well, what problems employees have, and recommend two improvements."),
        "points": ["what works well", "the main problems", "two recommendations with reasons"],
        "words": [140, 190], "minutes": 40,
    },
    {
        "id": "b2-article-skill",
        "exam": "b2_first_part2", "genre": "article", "register": "neutral",
        "title": "Article: a skill I learned",
        "prompt": ("You see this announcement in an international magazine: “Articles wanted: A skill that changed "
                   "my life. What skill did you learn, how did you learn it and how has it changed your life?” "
                   "Write your article."),
        "points": ["the skill and how you learned it", "difficulties you had", "how it changed your life"],
        "words": [140, 190], "minutes": 40,
    },
    {
        "id": "b2-email-english-course",
        "exam": "b2_first_part2", "genre": "email_semi", "register": "semi-formal",
        "title": "Email: questions about a course",
        "prompt": ("You want to take an intensive English course abroad next summer. Write an email to the language "
                   "school asking for information."),
        "points": ["dates and level of the courses", "accommodation options", "price and what is included"],
        "words": [140, 190], "minutes": 40,
    },
]

TASKS_BY_ID: dict[str, dict] = {t["id"]: t for t in TASKS}


def tasks_payload() -> dict:
    return {
        "tasks": [t | {"exam_label": EXAMS[t["exam"]], "genre_label": GENRES[t["genre"]]} for t in TASKS],
        "exams": [{"id": k, "label": v} for k, v in EXAMS.items()],
        "genres": [{"id": k, "label": v} for k, v in GENRES.items()],
    }
