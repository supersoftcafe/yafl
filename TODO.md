
# Replace worker nodes with tasks

Currently the task job system uses worker nodes that the caller pre-allocates. The async model of yafl
uses task objects, again that are pre-allocated. Instead of having two separate things both are tasks.

A task object then has fields to support queueing as a job, and a thread_id of the creator. A normal
dispatch will post it to the caller thread. Most code will invoke a task directly, if possible.

When adding parallel job support (future work) we'll have a dispatch that round robins the threads, but
for now the default mode of dispatch will be to put the job back on to the caller thread's queue. This
is good for cache coherency.

This means adding extra fields to task_t, and investigating any uses of the task API, to ensure that
they use the library task_init (to be done) method. Some of the new task code initialises explicitly
but that means that they assume that they know how to initialise. The first field of all task sub-classes
must be task_t, and task_init must be used on it.

