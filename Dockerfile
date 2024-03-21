FROM amazonlinux:2023

WORKDIR /usr/src/app

RUN rm -rf /var/lib/apt/lists/*

RUN dnf check-update && dnf upgrade -y
RUN dnf install git python3 python3-pip python3-setuptools -y

COPY *.txt ./

RUN pip3 install --no-cache-dir -r requirements.txt

COPY App.py .
COPY pages/ pages/
COPY utils/ utils/

#EXPOSE 8501
EXPOSE 8080

#HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1
HEALTHCHECK CMD curl --fail http://localhost:8080/_stcore/health || exit 1

RUN groupadd -r streamlit && useradd --no-log-init -r -g streamlit streamlit
RUN chown -R streamlit:streamlit /usr/src/app
USER streamlit


ENTRYPOINT [ "streamlit", "run", "App.py", \
             "--logger.level", "info", \
             "--browser.gatherUsageStats", "false", \
             "--browser.serverAddress", "0.0.0.0", \
             "--server.enableCORS", "false", \
             "--server.enableXsrfProtection", "false", \
             "--server.port", "8080"]
