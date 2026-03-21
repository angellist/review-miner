Task(
    subagent_type="general-purpose",
    description="Synthesize insights for topic: {topic}",
    prompt='''
Update best practices library for topic: {topic}

Follow: {prompt_file}
Library file: {library_file}
Insights file: {insights_file}
Threads file: {threads_file}
Insight count: {insight_count} insights for this topic

Output: {library_file} (update in place)
    '''
)
