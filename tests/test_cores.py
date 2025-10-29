
# heavy_multi.py
import multiprocessing
import time
import os

def is_prime(n: int) -> bool:
    """Simple but CPU-heavy primality test."""
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    for i in range(3, int(n ** 0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def worker(task_id: int, start: int, end: int) -> int:
    """Count primes in a given range."""
    pid = os.getpid()
    print(f"[Task {task_id}] PID {pid} starting range({start}, {end})...")
    count = sum(1 for n in range(start, end) if is_prime(n))
    print(f"[Task {task_id}] PID {pid} done. Found {count} primes.")
    return count


if __name__ == "__main__":
    start_time = time.time()

    # Use all available CPUs
    num_cpus = os.cpu_count() or 2
    print(f"Using {num_cpus} CPU cores...")

    # Split the number range across workers
    # Each will handle about 2.5 million numbers (tweak to adjust runtime)
    total_range = 10_000_000
    chunk_size = total_range // num_cpus

    ranges = [
        (i + 1, i * chunk_size, (i + 1) * chunk_size)
        for i in range(num_cpus)
    ]

    with multiprocessing.Pool(processes=num_cpus) as pool:
        results = [pool.apply_async(worker, args=r) for r in ranges]
        counts = [r.get() for r in results]

    total_primes = sum(counts)
    elapsed = time.time() - start_time
    print(f"Total primes found: {total_primes}")
    print(f"Completed in {elapsed:.2f} seconds.")
