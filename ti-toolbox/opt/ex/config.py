import os, re, sys, argparse

class ConfigError(Exception): pass

def validate_electrode(name): return bool(re.match(r'^[A-Za-z][A-Za-z0-9]*$', name))

def validate_current(value, min_val=0.0, max_val=None):
    return value > min_val and (max_val is None or value <= max_val)

def validate_env():
    required = ['PROJECT_DIR', 'SUBJECT_NAME', 'SELECTED_EEG_NET', 'LEADFIELD_HDF', 'ROI_NAME']
    config, missing = {}, []
    for var in required:
        val = os.getenv(var)
        if not val: missing.append(var)
        else: config[var] = val
    if missing: raise ConfigError(f"Missing env vars: {', '.join(missing)}")
    if not os.path.exists(config['LEADFIELD_HDF']): raise ConfigError("Leadfield file not found")
    return config

class ElectrodeConfig:
    def __init__(self, logger): self.logger = logger

    def get_electrodes(self, prompt):
        while True:
            try:
                electrodes = input(f"[INPUT] {prompt}").strip().replace(',', ' ').split()
                if all(validate_electrode(e) for e in electrodes):
                    self.logger.info(f"Accepted: {electrodes}")
                    return electrodes
                invalid = [e for e in electrodes if not validate_electrode(e)]
                self.logger.error(f"Invalid: {invalid}")
            except (EOFError, KeyboardInterrupt):
                self.logger.error("Input cancelled")
                sys.exit(1)
            self.logger.error("Enter valid electrode names")

    def get_config(self, all_combinations):
        if all_combinations:
            print("\n\033[1;36m=== All Combinations Mode ===\033[0m")
            print("\033[0;36mSearch all possible electrode assignments\033[0m")
            all_electrodes = self.get_electrodes("All electrodes (space/comma separated): ")
            return {'E1_plus': all_electrodes, 'E1_minus': all_electrodes,
                   'E2_plus': all_electrodes, 'E2_minus': all_electrodes}
        else:
            print("\n\033[1;36m=== Bucketed Mode ===\033[0m")
            print("\033[0;36mElectrodes grouped into E1+/- and E2+/- channels\033[0m")
            return {
                'E1_plus': self.get_electrodes("E1+ electrodes: "),
                'E1_minus': self.get_electrodes("E1- electrodes: "),
                'E2_plus': self.get_electrodes("E2+ electrodes: "),
                'E2_minus': self.get_electrodes("E2- electrodes: ")
            }

class CurrentConfig:
    def __init__(self, logger): self.logger = logger

    def get_param(self, name, default, validation_fn=None):
        try:
            import select
            if select.select([sys.stdin], [], [], 0.0)[0]:
                val = float(input().strip())
                if validation_fn is None or validation_fn(val):
                    self.logger.info(f"{name} from stdin: {val}")
                    return val
        except: pass
        env_val = os.getenv(name.upper().replace(' ', '_'))
        if env_val:
            try:
                val = float(env_val)
                if validation_fn is None or validation_fn(val):
                    self.logger.info(f"{name} from env: {val}")
                    return val
            except: self.logger.warning(f"Invalid {name} in env: {env_val}")
        self.logger.info(f"{name} default: {default}")
        return default

    def get_config(self):
        print("\n\033[1;36m=== Current Configuration ===\033[0m")
        print("\033[0;36mExample: total=2.0mA, step=0.2mA, limit=1.6mA\033[0m")
        print("\033[0;36mCh1: 1.6mA, Ch2: 0.4mA → Ch1: 0.4mA, Ch2: 1.6mA\033[0m\n")
        total = self.get_param('total_current', 1.0, lambda x: validate_current(x, 0))
        step = self.get_param('current_step', 0.1, lambda x: validate_current(x, 0, total))
        limit = self.get_param('channel_limit', None)
        limit = limit if limit and validate_current(limit, 0, total) else None
        return {'total_current': total, 'current_step': step, 'channel_limit': limit}

def parse_args():
    parser = argparse.ArgumentParser(description='TI Exhaustive Search')
    parser.add_argument('--all-combinations', action='store_true',
                       help='Search all electrode combinations')
    return parser.parse_args()

def get_full_config(logger):
    args = parse_args()
    env = validate_env()
    electrodes = ElectrodeConfig(logger).get_config(args.all_combinations)
    currents = CurrentConfig(logger).get_config()
    return {'environment': env, 'electrodes': electrodes, 'currents': currents,
           'all_combinations': args.all_combinations}
