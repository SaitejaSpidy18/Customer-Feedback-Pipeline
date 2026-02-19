# Customer Feedback Pipeline
Imagine you’re capturing thousands of customer comments every day. You want insights now, but you don’t want your API to crawl whenever traffic spikes. This project shows how to solve that with an event‑driven architecture: feedback comes in through a lightweight API, flows through Kafka, gets analyzed by a worker, and ends up in MySQL ready to be queried. It’s small enough to run on your laptop, but structured like a real system you’d see in production.

1. What this project actually does
Let’s start with the storyline:

A client sends feedback (who said what, and when).

The API does not process it directly; it just validates and fires an event into Kafka.

A separate worker picks up that event from Kafka, runs sentiment analysis, and writes results to MySQL.

The API can then serve queries on top of that processed data.

In other words, this isn’t “API → DB, done”, but “API → Kafka → Worker → DB → API”. That’s the core event‑driven idea: ingestion and processing are decoupled so each part can scale and fail independently.

2. How the pieces talk to each other
Let’s walk through the flow like a request journey.

Client → API
A client calls POST /feedback with three fields:

customer_id (for example: CUST001)

feedback_text (for example: “This product is amazing!”)

timestamp (for example: 2026‑02‑19T14:30:00Z)

The API checks:

Are all fields present?

Are customer_id and feedback_text non‑empty?

Is timestamp a valid ISO 8601 string?

If anything’s off, the API replies with a 400 status and a clear error message.

API → Kafka
If the payload is valid, the API generates a new UUID as message_id and builds a JSON payload that looks like:
message_id: <uuid>, customer_id: <string>, feedback_text: <string>, feedback_timestamp: <timestamp>

It sends this to a Kafka topic called customer_feedback_events, using kafka-python as the producer.
The important bit: the API then immediately returns 202 Accepted with that message_id, instead of waiting for any heavy processing to complete.

Kafka → Worker
On the other side, a worker service is subscribed to customer_feedback_events. It sits in a loop reading messages as they arrive. For each message, it does a quick sanity check: the JSON must contain message_id, customer_id, feedback_text, and feedback_timestamp. If the message is malformed, it logs the problem and moves on instead of crashing.

Worker → Sentiment analysis → MySQL
Now the fun part: the worker runs the feedback_text through NLTK’s VADER sentiment analyzer. VADER gives you a “compound” score between ‑1 and 1. The worker translates this into a simple label:

compound ≥ 0.05 → positive

compound ≤ ‑0.05 → negative

otherwise → neutral

It then writes a row into the feedback_analysis table in MySQL with:

message_id

customer_id

feedback_text

sentiment_score (positive/negative/neutral)

feedback_timestamp

analysis_timestamp (when the worker ran the analysis)

To avoid duplicates if Kafka replays a message, the worker uses message_id as the primary key and inserts using an “ignore on duplicate” approach. If the row already exists, it logs that and skips – that’s your idempotency guarantee.

Client → API (read side)
Once the worker has stored the data, the API can read it back:

GET /feedback/{message_id}: looks up that exact row in MySQL and returns it if it exists, or 404 if it doesn’t.

GET /feedback?sentiment=positive&page=1&limit=10: fetches a page of feedback items that match a given sentiment, with pagination handled via the usual page and limit parameters.

If you visualize it, you can think of it like this in your head:
Client → POST /feedback → API → Kafka topic customer_feedback_events → Worker → MySQL → API → GET /feedback…

3. Tech stack at a glance
Here’s what you’re actually running:

Python 3.11 for both the API and worker.

Flask for the REST API.

Apache Kafka (with Zookeeper) as the message broker.

MySQL 8 as persistent storage.

NLTK VADER for lightweight, rule‑based sentiment analysis.

Docker + Docker Compose to run everything together with one command.

Nothing exotic, but all the pieces are what you’d find in real‑world systems.

4. How to get it running (locally)
Let’s go step by step like you would actually do on your machine.

Make sure you have the basics

Docker

Docker Compose

Git

Grab the code

Clone your repository with a standard git clone command.

Change into the project directory.

Configure your environment
In the root of the project, there is an .env.example file. It lists all the environment variables the services expect, such as the Kafka broker address and MySQL credentials.

Copy .env.example to .env.

If you want, tweak the values (for example, change the MySQL password or database name).

By default, everything is wired so that:

Kafka is reachable at kafka:9092.

MySQL runs with a root password and a database called feedback_db.

These match the values in docker-compose.yml, so you don’t need to change anything to get started.

Start the whole stack
From the project root, use Docker Compose to build and run all services. The first run will take a bit longer as it pulls images and installs Python dependencies. Kafka and MySQL need a moment to warm up, so give it a short pause before testing the API.

Check that things are alive

Hit http://localhost:5000/health in a browser or API client. You should get a simple JSON “healthy” response.

If something looks off, you can inspect logs for the API and worker containers and see what’s going on.

When you’re done
It’s just as simple to stop everything and clean up containers and volumes using Docker Compose. That keeps your local environment tidy.

5. Playing with the API
Once everything is up, you interact with a few simple endpoints.

Health check
Whenever you want to know if the API is up, call GET /health.
You should see a 200 OK and a tiny JSON payload that says the service is healthy. This is also what Docker uses as a health check.

Sending feedback
The main entry point is POST /feedback. You send a JSON body that looks like:

customer_id: for example "CUST001"

feedback_text: for example "Really happy with the service!"

timestamp: for example "2026-02-19T14:30:00Z"

If you send:

Missing fields → you get a clear 400 error.

Empty customer_id or feedback_text → also 400.

An invalid timestamp like "yesterday" → again 400, with a message telling you the format is wrong.

If everything is okay, the response comes back with:

HTTP status 202 Accepted.

A JSON body containing a human‑readable message and a message_id (a UUID) that uniquely identifies your feedback event.

At this point, the message is in Kafka, but it might not yet be in MySQL. The idea is: “we accepted it and queued it for processing.”

Getting one feedback back
Once the worker has done its job, you can retrieve the full details with GET /feedback/{message_id}.

Possible outcomes:

If the worker has processed it, you get a JSON object with:

message_id

customer_id

feedback_text

sentiment_score (positive / negative / neutral)

feedback_timestamp (what you sent originally)

analysis_timestamp (when the worker analyzed it)

If it’s not there (either not processed yet or an invalid id), you get 404 Not Found.

Browsing by sentiment
For exploring the data, there’s GET /feedback?sentiment=...&page=...&limit=....

You pass:

sentiment as one of positive, negative, or neutral.

page (optional, defaults to 1).

limit (optional, defaults to 10).

If you send a sentiment that is not one of those three, the API will answer with a 400 and tell you what values are allowed. Otherwise, it will return a JSON object that includes:

feedback: an array of rows matching that sentiment.

page: the page you asked for.

limit: how many items per page.

sentiment: the sentiment you filtered by.

This endpoint is handy when you want to, for example, quickly look at all positive feedback on the first page.

6. What the database looks like
Behind the scenes, everything ends up in a single MySQL table called feedback_analysis. The columns are:

message_id (string, primary key, 36 chars for a UUID)

customer_id (string, required)

feedback_text (text, required)

sentiment_score (string, required – positive/negative/neutral)

feedback_timestamp (datetime, required)

analysis_timestamp (datetime, required)

On top of that, the table has indexes on:

customer_id

sentiment_score

feedback_timestamp

Those indexes make queries by sentiment or time more efficient. The table is created automatically on startup using the SQL in db/init.sql, which Docker mounts into MySQL at initialization.

7. A peek into the implementation
The API side
The Flask app:

Loads configuration from environment variables (via python-dotenv).

Creates a KafkaProducer that points to the broker defined by KAFKA_BROKER (for example, kafka:9092).

Uses JSON serialization for messages and configures a few retries to handle transient issues.

Connects to MySQL using pymysql and the MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE variables.

Logs key events such as:

Feedback accepted and published.

Database queries for GET endpoints.

Errors when something goes wrong.

The POST /feedback route contains the validation and the producer send. The /health route is intentionally minimal – it just returns a JSON status so that Docker and you can quickly see if the service is up.

The worker side
The worker:

Reads the same environment variables for Kafka and MySQL.

Creates a KafkaConsumer subscribed to customer_feedback_events with a specific group_id (for example, sentiment_analyzer_group_v1) so that you can scale out more workers in the future if you want.

Disables automatic offset commits so it can manually commit only after successful processing.

The processing loop works like this:

For each incoming message, parse the JSON value.

Confirm that message_id, customer_id, feedback_text, and feedback_timestamp are present; if not, log the issue and move on.

Run feedback_text through NLTK’s VADER SentimentIntensityAnalyzer.

Convert the compound score into a label:

≥ 0.05 → positive;

≤ ‑0.05 → negative;

everything else → neutral.

Open a connection to MySQL and try to insert a new row into feedback_analysis.

Use a “do nothing on duplicate primary key” approach so that if Kafka replays the same message, the worker just logs that it was already processed and doesn’t create a second row.

Only after the database write succeeds does the worker commit the Kafka offset, so processed messages aren’t lost.

Errors like JSON decoding failures, DB connection problems, or unexpected exceptions are logged with enough detail to debug later. For serious issues, the worker can pause briefly before trying again, so it doesn’t spin aggressively while a dependency is down. In a more advanced version, you’d send problematic messages to a dead‑letter topic, but for this assignment, robust logging and safe skipping behavior are enough to show you understand the pattern.

8. Testing the behavior
There are initial tests for the API that focus on quick wins:

“Is the /health endpoint up and returning 200?”

“Does POST /feedback with a valid body return 202 and a message_id?”

You can run them using pytest, either inside the container or in a local Python virtual environment. From there, it’s straightforward to extend the tests to cover things like invalid JSON, missing fields, invalid timestamps, pagination edge cases, and database lookups. The idea is to treat tests as a living safety net rather than a checkbox.

9. Why it’s built this way
A few design decisions are worth calling out.

Asynchronous by design
The API’s job is to accept input and publish events, not to crunch sentiment in the request path. This keeps the API fast and predictable under load. Even if Kafka or the worker slows down, clients still get quick acknowledgments.

Kafka as the backbone
Kafka is built for exactly this kind of event‑driven pattern: it handles high throughput, persists messages durably, and lets you add more consumers later without touching the producers. That means today you have a sentiment worker; tomorrow you could have another service that builds dashboards or raises alerts, all consuming from the same topic.

Idempotent processing
Kafka doesn’t guarantee “exactly once” in all scenarios without extra configuration, so it’s safer to design your consumer as if it might see duplicates. Using message_id as a primary key plus an “ignore on duplicate insert” strategy makes replays harmless.

Configuration via environment
All “moving parts” (broker address, DB credentials, etc.) live in environment variables. Only .env.example is committed, so you can show others how to configure the app without leaking secrets. .env stays local and out of Git.

One topic, simple mental model
There’s just one topic, customer_feedback_events. For teaching and assignment purposes, that’s perfect: you don’t get lost hopping between multiple topics, and the core concept stands out clearly.

10. Where you could take this next
If you want to push this project further, here are a few natural directions:

Introduce a proper dead‑letter topic for messages that repeatedly fail in the worker, so you can inspect them separately later.

Add authentication around the API (API keys, JWT, or OAuth) to make it look more “production”.

Wire in metrics and tracing (Prometheus, OpenTelemetry) so you can see how many messages you’re processing and where time is spent.

Swap out VADER for a more advanced model or a cloud NLP service if you need better sentiment accuracy.

Break the services into separate repositories, add CI pipelines, and deploy them to a cloud platform.

But even without those extras, this setup already demonstrates the key skills: event‑driven architecture, Kafka integration, asynchronous processing, idempotent consumers, containerization, and a clean API surface that’s easy to reason about.