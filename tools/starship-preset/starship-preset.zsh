# starship-preset — point Starship at the config picked for this directory.
# bin/starship-preset writes the picks. This reads them before every prompt,
# with no forks, so every open shell follows a new pick on its next prompt.
# A project pick (longest matching dir) beats the everywhere pick.

_starship_preset_state="${XDG_STATE_HOME:-$HOME/.local/state}/starship-preset"

_starship_preset_pick() {
  local dir p f best= bestdir=
  if [[ -r $_starship_preset_state/projects ]]; then
    while IFS=$'\t' read -r p f; do
      [[ $PWD/ == $p/* && ${#p} -gt ${#bestdir} ]] && { bestdir=$p; best=$f; }
    done < $_starship_preset_state/projects
  fi
  [[ -n $best && -r $best ]] || best=
  [[ -z $best && -r $_starship_preset_state/global ]] && best=$(<$_starship_preset_state/global)
  if [[ -n $best && -r $best ]]; then
    export STARSHIP_CONFIG=$best
  else
    unset STARSHIP_CONFIG
  fi
}

precmd_functions+=(_starship_preset_pick)
