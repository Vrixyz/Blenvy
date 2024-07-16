use std::any::TypeId;

use bevy::gltf::Gltf;
use bevy::prelude::*;
use bevy::scene::SceneInstance;
// use bevy::utils::hashbrown::HashSet;

use crate::{BlueprintAnimationPlayerLink, BlueprintAnimations, BlueprintInfo, BlueprintReadyForPostProcess, BlueprintInstanceReady, BlueprintSpawning, SubBlueprintSpawnRoot, SubBlueprintsSpawnTracker};
use crate::{SpawnBlueprint, Spawned};
use crate::{
    BlueprintEvent, CopyComponents, InBlueprint, NoInBlueprint, OriginalChildren
};




/// this system is in charge of doing any necessary post processing after a blueprint scene has been spawned
/// - it removes one level of useless nesting
/// - it copies the blueprint's root components to the entity it was spawned on (original entity)
/// - it copies the children of the blueprint scene into the original entity
/// - it add `AnimationLink` components so that animations can be controlled from the original entity
/// - it cleans up/ removes a few , by then uneeded components
pub(crate) fn spawned_blueprint_post_process( // rename to '
    unprocessed_entities: Query<
        (
            Entity,
            &Children,
            &OriginalChildren,
            &BlueprintAnimations,
            Option<&NoInBlueprint>,
            Option<&Name>,
            &BlueprintInfo,

            // sub blueprint instances tracker
            Option<&SubBlueprintSpawnRoot>
        ),
        (With<SpawnBlueprint>, With<SceneInstance>, Added<BlueprintReadyForPostProcess>),
    >,
    added_animation_players: Query<(Entity, &Parent), Added<AnimationPlayer>>,
    all_children: Query<&Children>,

    mut trackers: Query<(Entity, &mut SubBlueprintsSpawnTracker, &BlueprintInfo)>,


    mut commands: Commands,
    mut blueprint_events: EventWriter<BlueprintEvent>,

) {
    for (original, children, original_children, animations, no_inblueprint, name, blueprint_info, track_root) in
        unprocessed_entities.iter()
    {
        info!("post processing blueprint for entity {:?}", name);

        if children.len() == 0 {
            warn!("timing issue ! no children found, please restart your bevy app (bug being investigated)");
            continue;
        }
        // the root node is the first & normally only child inside a scene, it is the one that has all relevant components
        let mut root_entity = Entity::PLACEHOLDER; //FIXME: and what about childless ones ?? => should not be possible normally
                                                   // let diff = HashSet::from_iter(original_children.0).difference(HashSet::from_iter(children));
                                                   // we find the first child that was not in the entity before (aka added during the scene spawning)
        for c in children.iter() {
            if !original_children.0.contains(c) {
                root_entity = *c;
                break;
            }
        }

        // we flag all children of the blueprint instance with 'InBlueprint'
        // can be usefull to filter out anything that came from blueprints vs normal children
        if no_inblueprint.is_none() {
            for child in all_children.iter_descendants(root_entity) {
                commands.entity(child).insert(InBlueprint); // we do this here in order to avoid doing it to normal children
            }
        }

        // copy components into from blueprint instance's root_entity to original entity
        commands.add(CopyComponents {
            source: root_entity,
            destination: original,
            exclude: vec![TypeId::of::<Parent>(), TypeId::of::<Children>()],
            stringent: false,
        });

        // we move all of children of the blueprint instance one level to the original entity
        if let Ok(root_entity_children) = all_children.get(root_entity) {
            for child in root_entity_children.iter() {
                // info!("copying child {:?} upward from {:?} to {:?}", names.get(*child), root_entity, original);
                commands.entity(original).add_child(*child);
            }
        }

        if animations.named_animations.keys().len() > 0 {
            for (added, parent) in added_animation_players.iter() {
                if parent.get() == root_entity {
                    // FIXME: stopgap solution: since we cannot use an AnimationPlayer at the root entity level
                    // and we cannot update animation clips so that the EntityPaths point to one level deeper,
                    // BUT we still want to have some marker/control at the root entity level, we add this
                    commands
                        .entity(original)
                        .insert(BlueprintAnimationPlayerLink(added));
                }
            }
        }

        commands.entity(original).remove::<SpawnBlueprint>();
        commands.entity(original).remove::<Spawned>();
        // commands.entity(original).remove::<Handle<Scene>>(); // FIXME: if we delete the handle to the scene, things get despawned ! not what we want
        //commands.entity(original).remove::<BlueprintAssetsLoadState>(); // also clear the sub assets tracker to free up handles, perhaps just freeing up the handles and leave the rest would be better ?
        //commands.entity(original).remove::<BlueprintAssetsLoaded>();
        commands.entity(root_entity).despawn_recursive(); // Remove the root entity that comes from the spawned-in scene
        commands.entity(original).insert(            Visibility::Visible
        );

        commands.entity(original)
        .insert(BlueprintInstanceReady)
        .remove::<BlueprintSpawning>()
        

        //
        .remove::<BlueprintReadyForPostProcess>()
        ;


        if let Some(track_root) = track_root {
            //println!("got some root");
            if let Ok((s_entity, mut tracker, bp_info)) = trackers.get_mut(track_root.0) {
                // println!("found the tracker, setting loaded for {}", entity);
                tracker.sub_blueprint_instances.entry(original).or_insert(true);
                tracker.sub_blueprint_instances.insert(original, true);

                // TODO: ugh, my limited rust knowledge, this is bad code
                let mut all_spawned = true;

                for key in tracker.sub_blueprint_instances.keys() {
                    let val = tracker.sub_blueprint_instances[key];
                    println!("Key: {key}, Spawned {}", val);
                }

                for val in tracker.sub_blueprint_instances.values() {
                    println!("spawned {}", val);
                    if !val {
                        all_spawned = false;
                        break;
                    }
                }
                if all_spawned { // TODO: move this to an other system, or "notify" the tracked root entity of the fact that all its sub blueprints have been loaded
                    println!("ALLLLL SPAAAAWNED for {}", track_root.0);
                    // commands.entity(track_root.0).insert(bundle)
                    blueprint_events.send(BlueprintEvent::Spawned {entity: track_root.0, blueprint_name: bp_info.name.clone(), blueprint_path: bp_info.path.clone()});

                } 
            }
            
        } 
        if trackers.get(original).is_err() {
            // if it has no sub blueprint instances
            blueprint_events.send(BlueprintEvent::Spawned {entity: original, blueprint_name: blueprint_info.name.clone(), blueprint_path: blueprint_info.path.clone()});
        }
        
        debug!("DONE WITH POST PROCESS");
        info!("done instanciating blueprint for entity {:?}", name);

    }
}