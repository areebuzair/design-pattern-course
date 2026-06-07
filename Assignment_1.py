import os
import json
import time
from abc import ABC, abstractmethod

# 1. TEMPLATE METHOD & STRATEGY INTERFACE


class StorageStrategy(ABC):
    def __init__(self, filename: str, key: str):
        self.filename = filename
        self.key = key
        self.file = None

    # This is the Template Method. It defines the skeleton of the algorithm.
    def start(self) -> list:
        if os.path.exists(self.filename):
            return self._load_data()
        else:
            self._create_file()
            return []

    @abstractmethod
    def _load_data(self) -> list:
        pass

    @abstractmethod
    def _create_file(self):
        pass

    @abstractmethod
    def write(self, data: dict):
        pass

    @abstractmethod
    def close(self):
        pass

# 2. CONCRETE STRATEGIES


class JsonStrategy(StorageStrategy):
    def __init__(self, filename: str, key: str):
        super().__init__(filename, key)
        self._temp_data = []  # JSON needs to keep array in memory to dump at the end

    def _load_data(self) -> list:
        with open(self.filename, 'r', encoding='utf-8') as f:
            try:
                self._temp_data = json.load(f)
            except json.JSONDecodeError:
                self._temp_data = []
        return [datum.get(self.key) for datum in self._temp_data if self.key in datum]

    def _create_file(self):
        self._temp_data = []

    def write(self, data: dict):
        self._temp_data.append(data)

    def close(self):
        # JSON writes everything out at the explicit close trigger
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self._temp_data, f, indent=4)


class JsonlStrategy(StorageStrategy):
    def _load_data(self) -> list:
        keys = []
        with open(self.filename, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    datum = json.loads(line)
                    if self.key in datum:
                        keys.append(datum[self.key])
        # Open in append mode for continuous writing
        self.file = open(self.filename, 'a', encoding='utf-8')
        return keys

    def _create_file(self):
        self.file = open(self.filename, 'w', encoding='utf-8')

    def write(self, data: dict):
        if not self.file or self.file.closed:
            self.file = open(self.filename, 'a', encoding='utf-8')
        self.file.write(json.dumps(data) + '\n')
        self.file.flush()

    def close(self):
        if self.file and not self.file.closed:
            self.file.close()

# 3. DECORATOR PATTERN


class StrategyDecorator(StorageStrategy):
    """Base decorator class acting as a wrapper."""

    def __init__(self, wrapped: StorageStrategy):
        self._wrapped = wrapped
        super().__init__(wrapped.filename, wrapped.key)

    def start(self) -> list:
        return self._wrapped.start()

    def _load_data(self) -> list:
        return self._wrapped._load_data()

    def _create_file(self):
        self._wrapped._create_file()

    def write(self, data: dict):
        self._wrapped.write(data)

    def close(self):
        self._wrapped.close()


class LoggerDecorator(StrategyDecorator):
    """Concrete decorator to add logging to the write function."""

    def write(self, data: dict):
        super().write(data)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        key_val = data.get(self.key, 'UNKNOWN')
        print(
            f"[{timestamp}] SUCCESS: Checkpoint written for {self.key} -> '{key_val}'")

# 4. FACTORY PATTERN


class CheckpointStrategyFactory:
    @staticmethod
    def get_strategy(filename: str, key: str, enable_logging: bool = True) -> StorageStrategy:
        _, ext = os.path.splitext(filename)

        if ext == '.json':
            strategy = JsonStrategy(filename, key)
        elif ext == '.jsonl':
            strategy = JsonlStrategy(filename, key)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

        if enable_logging:
            return LoggerDecorator(strategy)

        return strategy

# 5. MAIN CONTEXT CLASS


class Checkpoints:
    def __init__(self, file: str, key: str):
        self.filename = file
        self.key = key
        self.checkpoints: list[str] = []
        self.strategy = CheckpointStrategyFactory.get_strategy(
            self.filename, self.key)

    def start(self):
        self.checkpoints = self.strategy.start()
        return self  # Allows chaining if desired

    def exists(self, key_val) -> bool:
        return key_val in self.checkpoints

    def write(self, data: dict):
        key_val = data.get(self.key)
        if not self.exists(key_val):
            self.strategy.write(data)
            self.checkpoints.append(key_val)
        else:
            print(f"[SKIP] Key '{key_val}' already exists in checkpoints.")

    # --- PYTHONIC CONTEXT MANAGER REPLACEMENT FOR __del__ ---
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'strategy'):
            self.strategy.close()


# USAGE EXAMPLE USING 'WITH' BLOCKS
if __name__ == "__main__":
    # Test with JSONL using the Pythonic context manager
    print("--- JSONL Test ---")
    with Checkpoints("data.jsonl", key="id") as cp_jsonl:
        cp_jsonl.write({"id": "req_001", "response": "Hello World"})
        cp_jsonl.write({"id": "req_001", "response": "Duplicate!"})
        cp_jsonl.write(
            {"id": "req_002", "response": "Design Patterns are great"})
    # The file safely closes right here out of scope. No __del__ race conditions.

    # Test with JSON using the Pythonic context manager
    print("\n--- JSON Test ---")
    with Checkpoints("data.json", key="task_id") as cp_json:
        cp_json.write({"task_id": "T-100", "status": "completed"})
        cp_json.write({"task_id": "T-101", "status": "pending"})
    # The JSON array is guaranteed to dump safely here.
