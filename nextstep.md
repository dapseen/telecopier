Lets think about it, there are some things I think we need to fix  before we move forward.

1. The idea is whenever there is a new signal, most signal comes with TPs and its important we spread the lot size in all the Tps and entry, which means if we are risking 2k USD, everything goes into the TPs and entry. e.g if total lot size is 1.2 dont start the first order with 1.2, start with 1.2/(no of tps)
2. I also noticed that the trade execution is not perisisting into the DB, we need to keep trade transactions into the DB
3. We need to put master and slave architecture into mind , we are looking at runing 30 slaves
4. redis for process queue will come later

