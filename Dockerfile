# Use the official Python image from Docker Hub
FROM python:3.11-buster

# Set the working directory inside the container
WORKDIR /app


# install dependencies
RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port that Streamlit will run on
EXPOSE 8501
# Ensure that the entrypoint script is executable
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]

# Command to run the Streamlit app
CMD ["streamlit", "run", "start.py"]
