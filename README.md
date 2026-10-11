Please note that this file contains my experiences and learnings along with a short overview of technologies in my own words. For a formal documentation of the project, please refer to the README2.md file in the codebase.


How did I design this application-
Section 1 - UI--->
  The ui and frontend of this project is designed using streamlit. It is designed to be responsive and user-friendly.

Section 2 - Overall Architecture and Features--->
  Whenver the user opens the app, the user is prompted to upload a dataset in csv or excel file. The dataset is than prcessed by our backend. 

  Then the user can simply open our chatbot and ask any query about the dataset. The chatbot will then respond to the query. 

  Another intersting feature of this app is that the user can genrate a report of the dataset. This report will contain a short summary of what the data is about and what can be inferred from the data. Later, it will have many chart that give a visual representation of the data.

Section 3 - API Calling --->
  The agentic system is built using Groq api key. I have used openai/gpt-os-120b model to generate the response.
  
  Role of the agent- The agent will act as a data analyst and will be able to answer any query about the dataset. It is clearly instructed not to answer questions that are not related to the dataset so that the model is not exploited.

  System Prompt- The agent is asked to use the provided tools to compute statistics, aggregations, filters, correlations, outliers, or time trends. Never guess, estimate, or make up numbers. 

Section 4 - Tools --->
  The tools that i have included are the standard tools used in the data anylysis process.

  1. Filter Data- This tool simply uses pandas to mask the data based on the conditions provided by the user based on relational operators, string matching, etc. Than, the data is sorted based on the user provided columns and sent to the agent.

  2.Aggregate Data- Whenever the tool is required to do any computation on the data, the commands are normalized(converted to pandas commands) and than pandas groups the data into bins based on the required commands. These commands are executed sepeartely by pandas and the results are sent to the agent after being sorted.

  3.Statistical Analysis- This one is quite simple.
    First, we drop all the empty cells and calculate the mean, median, min, max, std, etc(based on requirements) for numerical data and for categorical data we simply count the number of unique values.

  4.Correlation Analysis- This is used to calculate the correlation between two columns, ie.
    evaluate changing trends.
    First, remove redundant coloums. Then, use itertools to pair every coloumn with every other coloumn. Both of these pairs are given a similarity score from -1 to 1. This helps to identify correlations between data.

  5.Outlier Detection- This tool is used to identify outliers in the data. Just check the lowest and highest values of the column and generate a middle value. Upper and lower bounds are defined as 1.5 times this value. If the value is outside these bounds, it is considered an outlier.

  6.Time Series Analysis- This tool is used to analyze time series data. We first convert messy time series data into a clean format using pandas. Then, since the chinging trends can be very noisy, we use the pollyfit liberary of numpy to smooth the data. This helps to identify trends and patterns in the data.

Section 5 - Visualization of Data --->
  The data can be easily visualized if the user asks for a chart. The python liberaries of matplotlib and seaborn are used to generate the charts. 
  These are displayed in the ui by making them interactive using plotly.
  The width and dimensions of the charts are controlled by streamlit.

Section 6 - Report Generation and Visualization --->
  When you click the Report button on the landing dock, the app runs an automated "evidence-first" pipeline (builder.py & pdf.py) that first uses Pandas and NumPy to execute our statistical, correlation, outlier, category-aggregation, and time-series tools across your entire dataset so every number is 100% mathematically verified before the AI writes a single word. That bundle of verified math and sample rows is then sent to the Groq LLM (openai/gpt-oss-120b), which acts as an executive writer and returns a structured report blueprint validated by Pydantic (ReportDraft)—complete with an Executive Summary, a friendly Plain-English Guide explaining what the dataset is about for non-technical readers, detailed analytical findings, and actionable recommendations (with an automatic deterministic fallback template if the API is ever offline). Next, Matplotlib and Seaborn (mpl_engine.py) paint high-resolution static charts into an in-memory byte stream (io.BytesIO), and ReportLab Platypus (pdf.py) typesets the entire document into a multi-page PDF with custom typography, callout boxes, schema tables, embedded chart figures, and a custom NumberedCanvas that stamps headers, footers, and "Page X of Y" numbers on every page. Finally, the finished PDF bytes are cached in Streamlit's session_state using a SHA-256 dataset fingerprint (hashlib) and served directly to browser via st.download_button, allowing instant one-click downloading without ever re-running the heavy calculations for the same file.


Section 7 - Persistent, Intelligent Memory (Supabase PostgreSQL) -->
  The application includes a persistent long-term memory system (backend/memory/) backed by Supabase PostgreSQL. Whenever the user asks to remember something, the agent will store it in the memory. The memory will be stored in the supabase database. Whenever the user asks for the same thing, the agent will retrieve it from the memory and implement it accordingly.

-------WHAT DID I LEARN FROM THIS PROJECT?-------

# Data Analytics Tool
1. Before building this project, I was aware about the agentic system, how we call llm and can set it to call tools. I was also aware about the concept of sending files and making llm analyse them. 
However, I was not familier with the data analysis tools of python and how greacefully we handle large datasets. This project gave me an ooppurtunity to learn about the data analysis tools of python and how to use them to analyse large datasets.

2. I had experience with seaborn and matplotlib but was not very familiar with plotly. This project compelled me to learn how to create and display interactive charts in frontend.

3. I was quite a beginner in postgreSQL and supabase. This project gave me an opportunity to learn how to use postgreSQL and supabase.


-------AN OBSERVATION--------

When I asked the system to generate a report for small datasets, it genrated box plots which were suitable to visualize the data. Hence, i made the system intelligent where it can detect the type of chart to be generated based on the dataset size and column structure.
Bar graphs and line graphs for small data and box plots for large data.


-------FUTURE IMPROVEMENTS--------

1. We can create a RAG based system that can help use not only anylyse tabular data but also large text documentations.
2. We can also design a tool to create datasets from huge data(based on RAG).
3. Further improve the UI by making it more proffesssional with the help of React and Tailwind(currently we are using streamlit).
4. Include a database to store chat history and login data to handle multiple users.




