FROM python:3.12-slim

WORKDIR /benchmark
COPY evaluator.py ./evaluator.py
COPY scenarios ./scenarios
COPY evaluate.sh ./evaluate.sh
RUN chmod +x ./evaluate.sh

ENTRYPOINT ["./evaluate.sh"]
