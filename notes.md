Engine refresh
Move span factory to slot 
Open resource holder in slot 
Engines provides all 3 handle methods implementation 
Slot and slot lease 
Slot lease can cache span and lifecycle so we should get lifecycle and span in slot, not inside the engine. Slot handle should get both span and span input, lifecycle and lifecycle input …. SLOT LEASE SHOULD BE ANOTHER OBJECT THAT PROVIDES CACHING 
Slot lease first handle and continue handle 

Resource holder an enter and an exit should be simple try except finally - sometimes we want to commit, sometimes not. This is done by slot or LeaseSlot 
 

Saga - on resource holder 
For slot provide in memory saga to store objects with 3 fields type, saga handler key, saga command. This will be turned into persistence on resource commit. So  this can be stored inside a resource holder! Saga persistence can be in memory or sql or Redis - it is placed inside resource holder and places this info on commit. This is a global object so its reference is both in direttore (to compensate) and in each resource holder to put this info 

First we persist saga than commit 

Saga can be for queries? 


2 versions of direttore - with slot pool and without 

Delete queries from direttore? Now the only difference between them is that queries without event handling 


Saga and turn off transaction inside use case handler - we can add to resource holder saga objects and then commit. This object will have a special flag version - we will execute the biggest version of every handle key 

On exception (on our slot try except) we should call slot compensate with a saga key. We schooled provide a list of saga objects and then open order they occurred - we will execute the last version for every handler. 


Saga handler on exception we should- when the handler is end but not committed - it is inside saga list, but there was an exception inside event handler 