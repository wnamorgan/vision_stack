import multiprocessing as mp
from video_process import run as video_run
from api_process import run as api_run
from udp_publisher import run as udp_run
from dash_process import run as dash_run


def main():
    mp.set_start_method("spawn")

    procs = [
        mp.Process(target=video_run, name="video"),
        mp.Process(target=api_run, name="api"),
        mp.Process(target=udp_run, name="udp"),
        mp.Process(target=dash_run, name="dash"),
    ]

    for p in procs:
        p.start()

    for p in procs:
        p.join()    

if __name__ == "__main__":
    main()
