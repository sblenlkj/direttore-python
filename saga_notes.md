Saga that registers objects to a different dct by saga key
- It add to the store by saga key. It stores objects with key + payload.
    - The db can be in memory / redis / sql rel db - for it we need the current session - provide resource holder 
- Saga for after transaction event handling 
- Before use case handle we can execute create saga key, we provide handler context. This key we will provide to on commit and on rollback. This is an operation ID. We can put it inside a direttore.handle 


- for some use cases I should not open the session 


Saga - use case handler can be saga handler. It has on commit and on rollback and accepts uui of the saga operation 