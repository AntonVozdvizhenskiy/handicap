#!/usr/bin/env python3

import os
import json
from datetime import datetime

result_path = '/opt/quake/handicap/games/'

last_game_json_file = '/opt/quake/qwserver/ffa/demoinfo_127.0.1.1_27501.json';

result_server_haindicap_config = '/opt/quake/qwserver/ffa/handicap.cfg'

last_games_for_analize     = 10
best_results_for_normalize = 3
kill_factor_limit          = 125
death_factor_limit         = 125

def deep_merge_with_summation(dict1, dict2):
    merged_dict = dict1.copy()
    for key, value in dict2.items():
        if key in merged_dict and isinstance(merged_dict[key], dict) and isinstance(value, dict):
            merged_dict[key] = deep_merge_with_summation(merged_dict[key], value)
        elif key not in merged_dict and  isinstance(value, dict):
            merged_dict[key] = deep_merge_with_summation({}, value)
        else:
            merged_dict.setdefault(key, 0)
            merged_dict[key] += value
    return merged_dict

def walk_through_hash_and_devide(dict1, divisor):
    for key, value in dict1.items():
        if isinstance(value, dict):
            walk_through_hash_and_devide(value, divisor)
        else:
            dict1[key] = value / divisor
    return dict1


class Handicap:

    def __init__(self):
        self.duration_factor = 1
        self.players_factor = 1
        self.last_game_hash = self.load_json_file(last_game_json_file)
        self.game_date_time = datetime.strptime(self.last_game_hash['date'], '%Y-%m-%d %H:%M:%S %z').strftime('%Y-%m-%d_%H:%M:%S')
        self.mapname = self.last_game_hash['map']

    def make(self):
        self.save_player_stat()
        self.calculate_handicap()

    def save_player_stat(self):
        self._duration_factor()
        self._players_factor()
        self.build_players_files()
  
    def calculate_handicap(self):
        self.get_players_names()
        self.calculate_average_player_result()
        self.calculate_normalizing_params()
        self.calcutate_handicap_for_each_player()
        self.save_handicap_config()

    def _duration_factor(self):
        if self.last_game_hash['duration'] < 300:
            quit()
        elif self.last_game_hash['duration'] >= 300:
            self.duration_factor = self.last_game_hash['duration'] / 600

    def _players_factor(self):
        self.players_factor = 1 / (len(self.last_game_hash['players']) - 1)

    def _applay_factors(self, value: int):
        return value * self.players_factor * self.duration_factor

    def make_player_dir(self, path):
        dirname = os.path.dirname(path)
        isExist = os.path.exists(dirname)
        if not isExist:
           os.makedirs(dirname)

    def load_json_file(self, filename: str):
        with open(filename) as f_in:
            return json.load(f_in)

    def save_player_game_json(self, result):
        filename = result_path + result['meta']['name'] + '/' + self.game_date_time + '_' + self.mapname + '.json'
        "".join([c for c in filename if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        self.make_player_dir(filename)
        jsonfile = open(filename, 'w')
        jsonfile.write(json.dumps(result, sort_keys = True, indent = 2))
        jsonfile.close()

    def build_players_files(self):
        for player in self.last_game_hash['players']:
            
            player_hash = {
                'meta': {
                    'name': player['name'],
                    'map':  self.mapname,
                    'date': self.game_date_time,
                },
                'amplifiers': {
                    'damage': player['amplifiers']['damage'],
                    'health': player['amplifiers']['health'],
                },
                'stats': {
                    'frags':    self._applay_factors(player['stats']['frags']),
                    'kills':    round (self._applay_factors(player['stats']['kills'])    / player['amplifiers']['damage'] * 100, 2) ,
                    'deaths':   round (self._applay_factors(player['stats']['deaths'])   / player['amplifiers']['health'] * 100, 2) ,
                    'suicides': round (self._applay_factors(player['stats']['suicides']) / player['amplifiers']['health'] * 100, 2) ,
                }
            }
            self.save_player_game_json(player_hash)
    
    def get_players_names(self):
        self.players = [ name for name in os.listdir(result_path) if os.path.isdir(os.path.join(result_path, name)) ]

    def calculate_average_player_result(self):
        self.avg_result = {}
        for player in self.players:
            res = os.listdir(result_path + player)
            res.sort()
            last_games = res[-last_games_for_analize:]
            merged_games_hash = {}
            for game in last_games:
                game_dict = self.load_json_file(result_path + player + '/' + game)
                merged_games_hash = deep_merge_with_summation(merged_games_hash, game_dict['stats'])
            self.avg_result[player] = walk_through_hash_and_devide(merged_games_hash, len(last_games))
        print (self.avg_result.items())    

    def calculate_normalizing_params(self):
        top_kill = [ stats['kills'] for player, stats in self.avg_result.items() ]
        bottom_death = [ stats['deaths'] + stats['suicides'] for player, stats in self.avg_result.items() ]
        top_kill.sort(reverse=True)
        bottom_death.sort()
        self.norm_kill = sum(top_kill[0:best_results_for_normalize]) / best_results_for_normalize
        self.norm_death = sum(bottom_death[0:best_results_for_normalize]) / best_results_for_normalize
        print (self.norm_kill)
        print (self.norm_death)

    def calcutate_handicap_for_each_player(self):
        self.damage_handicaps = { player: int(self.norm_kill / stats['kills'] * 100) 
                for player, stats in self.avg_result.items() 
                if self.norm_kill / stats['kills'] * 100 > kill_factor_limit }

        self.health_handicaps = { player: int((stats['deaths'] + stats['suicides']) / self.norm_death * 100) 
                for player, stats in self.avg_result.items() 
                if (stats['deaths'] + stats['suicides']) / self.norm_death * 100 > death_factor_limit }
        print (self.damage_handicaps)
        print (self.health_handicaps)


    def save_handicap_config(self):
        with open(result_server_haindicap_config, 'w') as f:
            print('//autogenerate by ' + __file__ + "\n", file=f)
            for player, value in self.damage_handicaps.items():
                print('set damage_amplifier_%s %d' % (player, value), file=f)
    
            for player, value in self.health_handicaps.items():
                print('set health_amplifier_%s %d' % (player, value), file=f)

Handicap().make()
