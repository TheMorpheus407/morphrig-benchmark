#include "MorphRigCharacter.h"
#include "MorphRig.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "UObject/ConstructorHelpers.h"

AMorphRigCharacter::AMorphRigCharacter()
{
	PrimaryActorTick.bCanEverTick = true;

	GetCapsuleComponent()->InitCapsuleSize(38.0f, 90.0f);

	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	GetCharacterMovement()->bOrientRotationToMovement = false;
	GetCharacterMovement()->MaxWalkSpeed = 420.0f;
	GetCharacterMovement()->JumpZVelocity = 520.0f;
	GetCharacterMovement()->AirControl = 0.35f;

	if (GetMesh())
	{
		// Blender character faces -Y; rotate mesh -90 deg Yaw so character faces +X in Unreal
		GetMesh()->SetRelativeLocation(FVector(0.0f, 0.0f, -90.0f));
		GetMesh()->SetRelativeRotation(FRotator(0.0f, -90.0f, 0.0f));
		GetMesh()->SetAnimationMode(EAnimationMode::AnimationCustomMode);
		GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
	}

	DialogueAudioComp = CreateDefaultSubobject<UAudioComponent>(TEXT("DialogueAudioComp"));
	DialogueAudioComp->SetupAttachment(RootComponent);
	DialogueAudioComp->bAutoActivate = false;

	PropCellComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PropCellComp"));
	PropCellComp->SetupAttachment(GetMesh());
	PropCellComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	PropCellComp->SetRelativeScale3D(FVector(0.03f, 0.03f, 0.08f));

	PropBeaconComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("PropBeaconComp"));
	PropBeaconComp->SetupAttachment(GetMesh());
	PropBeaconComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	PropBeaconComp->SetRelativeScale3D(FVector(0.08f, 0.08f, 0.05f));

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderFinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (CylinderFinder.Succeeded())
	{
		PropCellComp->SetStaticMesh(CylinderFinder.Object);
		PropBeaconComp->SetStaticMesh(CylinderFinder.Object);
	}
}

void AMorphRigCharacter::BeginPlay()
{
	Super::BeginPlay();
	InitializeCatalogAndLoadAssets();
}

void AMorphRigCharacter::InitializeCatalogAndLoadAssets()
{
	// Load Operative SkeletalMesh if available
	USkeletalMesh* SkelMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/MorphRig/Character/Operative.Operative"));
	if (!SkelMesh)
	{
		SkelMesh = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/MorphRig/Character/SK_Operative.SK_Operative"));
	}
	if (SkelMesh && GetMesh())
	{
		GetMesh()->SetSkeletalMeshAsset(SkelMesh);
		MorphAnimInstance = NewObject<UMorphRigAnimInstance>(GetMesh(), UMorphRigAnimInstance::StaticClass());
		GetMesh()->SetAnimInstanceClass(UMorphRigAnimInstance::StaticClass());
		MorphAnimInstance = Cast<UMorphRigAnimInstance>(GetMesh()->GetAnimInstance());
		if (!MorphAnimInstance)
		{
			MorphAnimInstance = NewObject<UMorphRigAnimInstance>(GetMesh());
		}

		// Attach physical props to their authored sockets/bones
		PropCellComp->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, TEXT("cell_socket_r"));
		PropBeaconComp->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, TEXT("prop_beacon"));
	}

	// Load Team A / Team B textures for dynamic material switching
	TexTeamA_D = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/T_Operative_Props_Accent_TeamA_D.T_Operative_Props_Accent_TeamA_D"));
	TexTeamA_E = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/T_Operative_Props_Accent_TeamA_E.T_Operative_Props_Accent_TeamA_E"));
	TexTeamB_D = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/T_Operative_Props_Accent_TeamB_D.T_Operative_Props_Accent_TeamB_D"));
	TexTeamB_E = LoadObject<UTexture2D>(nullptr, TEXT("/Game/MorphRig/Textures/T_Operative_Props_Accent_TeamB_E.T_Operative_Props_Accent_TeamB_E"));

	if (GetMesh() && GetMesh()->GetNumMaterials() > 5)
	{
		TeamAccentMID = GetMesh()->CreateAndSetMaterialInstanceDynamic(5);
	}

	// Load spoken dialogue audio
	DialogueSoundWave = LoadObject<USoundWave>(nullptr, TEXT("/Game/MorphRig/Audio/dialogue.dialogue"));
	if (DialogueSoundWave && DialogueAudioComp)
	{
		DialogueAudioComp->SetSound(DialogueSoundWave);
	}

	// Register all 96 required clips from required_animations.csv
	ClipRegistry.Empty();
	ClipIndexMap.Empty();

	auto AddClip = [&](const TCHAR* Id, const TCHAR* Cat, bool bLoop, bool bUpper, bool bAddHit,
		EMorphRigPriority Prio, const TCHAR* NextClip, TArray<FMorphRigEventMarker> InMarkers = {})
	{
		FMorphRigClipEntry Entry;
		Entry.ClipId = FName(Id);
		Entry.Category = Cat;
		Entry.bLooping = bLoop;
		Entry.bUpperBodyCapable = bUpper;
		Entry.bAdditiveHit = bAddHit;
		Entry.Priority = Prio;
		Entry.NextChainClip = NextClip ? FName(NextClip) : NAME_None;
		Entry.Markers = MoveTemp(InMarkers);

		const FString AssetPath = FString::Printf(TEXT("/Game/MorphRig/Animations/%s.%s"), Id, Id);
		Entry.Sequence = LoadObject<UAnimSequence>(nullptr, *AssetPath);

		const int32 Idx = ClipRegistry.Add(Entry);
		ClipIndexMap.Add(Entry.ClipId, Idx);
	};

	const TArray<FMorphRigEventMarker> GaitEvents = {
		{ TEXT("foot_l_contact"), 0.20f },
		{ TEXT("foot_r_contact"), 0.65f }
	};

	// 1. Idles (3)
	AddClip(TEXT("idle_relaxed"), TEXT("Idle"), true, false, false, EMorphRigPriority::Locomotion, nullptr);
	AddClip(TEXT("idle_combat"), TEXT("Idle"), true, false, false, EMorphRigPriority::Locomotion, nullptr);
	AddClip(TEXT("idle_wounded"), TEXT("Idle"), true, false, false, EMorphRigPriority::Locomotion, nullptr);

	// 2. Walk 8-Way (8)
	for (const TCHAR* WId : { TEXT("walk_f"), TEXT("walk_fl"), TEXT("walk_l"), TEXT("walk_bl"), TEXT("walk_b"), TEXT("walk_br"), TEXT("walk_r"), TEXT("walk_fr") })
	{
		AddClip(WId, TEXT("Locomotion_Walk"), true, false, false, EMorphRigPriority::Locomotion, nullptr, GaitEvents);
	}

	// 3. Run 8-Way + Sprint (9)
	for (const TCHAR* RId : { TEXT("run_f"), TEXT("run_fl"), TEXT("run_l"), TEXT("run_bl"), TEXT("run_b"), TEXT("run_br"), TEXT("run_r"), TEXT("run_fr"), TEXT("sprint_f") })
	{
		AddClip(RId, TEXT("Locomotion_Run"), true, false, false, EMorphRigPriority::Locomotion, nullptr, GaitEvents);
	}

	// 4. Starts, Stops, Turns, Pivots (6)
	AddClip(TEXT("start_f"), TEXT("Transitions"), false, false, false, EMorphRigPriority::Locomotion, TEXT("run_f"), GaitEvents);
	AddClip(TEXT("stop_f"), TEXT("Transitions"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"), GaitEvents);
	AddClip(TEXT("turn_l90"), TEXT("Transitions"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"), GaitEvents);
	AddClip(TEXT("turn_r90"), TEXT("Transitions"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"), GaitEvents);
	AddClip(TEXT("pivot_l180"), TEXT("Transitions"), false, false, false, EMorphRigPriority::Locomotion, TEXT("run_f"), GaitEvents);
	AddClip(TEXT("pivot_r180"), TEXT("Transitions"), false, false, false, EMorphRigPriority::Locomotion, TEXT("run_f"), GaitEvents);

	// 5. Jump, Fall, Land (5)
	AddClip(TEXT("jump_start"), TEXT("Jump_Fall"), false, false, false, EMorphRigPriority::JumpAir, TEXT("jump_air"));
	AddClip(TEXT("jump_air"), TEXT("Jump_Fall"), true, false, false, EMorphRigPriority::JumpAir, TEXT("jump_land"));
	AddClip(TEXT("jump_land"), TEXT("Jump_Fall"), false, false, false, EMorphRigPriority::JumpAir, TEXT("idle_combat"), GaitEvents);
	AddClip(TEXT("fall"), TEXT("Jump_Fall"), true, false, false, EMorphRigPriority::JumpAir, TEXT("land_heavy"));
	AddClip(TEXT("land_heavy"), TEXT("Jump_Fall"), false, false, false, EMorphRigPriority::JumpAir, TEXT("idle_combat"), GaitEvents);

	// 6. Root-Motion Dashes & Event Blink (6)
	const TArray<FMorphRigEventMarker> DashEvents = {
		{ TEXT("dash_start"), 0.03f },
		{ TEXT("dash_stop"), 0.36f }
	};
	for (const TCHAR* DId : { TEXT("dash_f"), TEXT("dash_b"), TEXT("dash_l"), TEXT("dash_r") })
	{
		AddClip(DId, TEXT("Dash_Blink"), false, false, false, EMorphRigPriority::EvadeDashBlink, TEXT("idle_combat"), DashEvents);
	}
	AddClip(TEXT("blink_out"), TEXT("Dash_Blink"), false, false, false, EMorphRigPriority::EvadeDashBlink, TEXT("blink_in"),
		{ { TEXT("blink_vanish"), 0.25f } });
	AddClip(TEXT("blink_in"), TEXT("Dash_Blink"), false, false, false, EMorphRigPriority::EvadeDashBlink, TEXT("idle_combat"),
		{ { TEXT("blink_appear"), 0.03f } });

	// 7. Melee 3-Hit Combo (3)
	const TArray<FMorphRigEventMarker> MeleeEvents = {
		{ TEXT("hit_window_start"), 0.16f },
		{ TEXT("hit_window_end"), 0.36f },
		{ TEXT("combo_window_open"), 0.30f },
		{ TEXT("combo_window_close"), 0.56f }
	};
	AddClip(TEXT("melee_1"), TEXT("Melee"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"), MeleeEvents);
	AddClip(TEXT("melee_2"), TEXT("Melee"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"), MeleeEvents);
	AddClip(TEXT("melee_3"), TEXT("Melee"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"), MeleeEvents);

	// 8. Ranged & Reload (3)
	AddClip(TEXT("ranged_fire"), TEXT("Ranged"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"),
		{ { TEXT("muzzle_flash"), 0.06f } });
	AddClip(TEXT("ranged_burst"), TEXT("Ranged"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"),
		{ { TEXT("muzzle_flash"), 0.06f }, { TEXT("muzzle_flash"), 0.18f }, { TEXT("muzzle_flash"), 0.30f } });
	AddClip(TEXT("reload"), TEXT("Ranged"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"),
		{ { TEXT("cell_eject"), 0.40f }, { TEXT("cell_insert"), 1.35f } });

	// 9. Cast, Channel, Charge, Deploy, Uplink (16)
	AddClip(TEXT("cast_directional"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"),
		{ { TEXT("muzzle_flash"), 0.26f } });
	AddClip(TEXT("cast_ground"), TEXT("Abilities"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));
	AddClip(TEXT("cast_self"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));

	AddClip(TEXT("channel_start"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("channel_loop"));
	AddClip(TEXT("channel_loop"), TEXT("Abilities"), true, true, false, EMorphRigPriority::CombatAbility, TEXT("channel_end"));
	AddClip(TEXT("channel_end"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));
	AddClip(TEXT("channel_interrupt"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));

	AddClip(TEXT("charge_start"), TEXT("Abilities"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("charge_hold"));
	AddClip(TEXT("charge_hold"), TEXT("Abilities"), true, false, false, EMorphRigPriority::CombatAbility, TEXT("charge_release"));
	AddClip(TEXT("charge_release"), TEXT("Abilities"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"),
		{ { TEXT("muzzle_flash"), 0.16f } });
	AddClip(TEXT("charge_cancel"), TEXT("Abilities"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));

	AddClip(TEXT("deploy"), TEXT("Abilities"), false, false, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"),
		{ { TEXT("object_release"), 0.72f } });

	AddClip(TEXT("uplink_start"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("uplink_loop"));
	AddClip(TEXT("uplink_loop"), TEXT("Abilities"), true, true, false, EMorphRigPriority::CombatAbility, TEXT("uplink_end"));
	AddClip(TEXT("uplink_end"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));
	AddClip(TEXT("uplink_cancel"), TEXT("Abilities"), false, true, false, EMorphRigPriority::CombatAbility, TEXT("idle_combat"));

	// 10. Additive Hit Reactions (4)
	for (const TCHAR* HId : { TEXT("hit_f"), TEXT("hit_b"), TEXT("hit_l"), TEXT("hit_r") })
	{
		AddClip(HId, TEXT("Hit_Reactions"), false, true, true, EMorphRigPriority::Locomotion, nullptr);
	}

	// 11. Stun, Knockback, Knockup, Knockdown, Prone, Getup, Sleep (15)
	AddClip(TEXT("stun_start"), TEXT("Crowd_Control"), false, false, false, EMorphRigPriority::CrowdControl, TEXT("stun_loop"));
	AddClip(TEXT("stun_loop"), TEXT("Crowd_Control"), true, false, false, EMorphRigPriority::CrowdControl, TEXT("stun_end"));
	AddClip(TEXT("stun_end"), TEXT("Crowd_Control"), false, false, false, EMorphRigPriority::CrowdControl, TEXT("idle_combat"));
	AddClip(TEXT("knockback"), TEXT("Crowd_Control"), false, false, false, EMorphRigPriority::CrowdControl, TEXT("idle_combat"));

	AddClip(TEXT("knockup_start"), TEXT("Knockdown"), false, false, false, EMorphRigPriority::Knockdown, TEXT("knockup_air"));
	AddClip(TEXT("knockup_air"), TEXT("Knockdown"), true, false, false, EMorphRigPriority::Knockdown, TEXT("knockdown_back"));
	AddClip(TEXT("knockdown_front"), TEXT("Knockdown"), false, false, false, EMorphRigPriority::Knockdown, TEXT("prone_front"));
	AddClip(TEXT("knockdown_back"), TEXT("Knockdown"), false, false, false, EMorphRigPriority::Knockdown, TEXT("prone_back"));
	AddClip(TEXT("prone_front"), TEXT("Knockdown"), true, false, false, EMorphRigPriority::Knockdown, TEXT("getup_front"));
	AddClip(TEXT("prone_back"), TEXT("Knockdown"), true, false, false, EMorphRigPriority::Knockdown, TEXT("getup_back"));
	AddClip(TEXT("getup_front"), TEXT("Knockdown"), false, false, false, EMorphRigPriority::Knockdown, TEXT("idle_combat"));
	AddClip(TEXT("getup_back"), TEXT("Knockdown"), false, false, false, EMorphRigPriority::Knockdown, TEXT("idle_combat"));

	AddClip(TEXT("sleep_start"), TEXT("Crowd_Control"), false, false, false, EMorphRigPriority::CrowdControl, TEXT("sleep_loop"));
	AddClip(TEXT("sleep_loop"), TEXT("Crowd_Control"), true, false, false, EMorphRigPriority::CrowdControl, TEXT("sleep_end"));
	AddClip(TEXT("sleep_end"), TEXT("Crowd_Control"), false, false, false, EMorphRigPriority::CrowdControl, TEXT("idle_combat"));

	// 12. Death, Dead Poses, Respawn (5)
	AddClip(TEXT("death_front"), TEXT("Death_Respawn"), false, false, false, EMorphRigPriority::Terminal, TEXT("dead_front"));
	AddClip(TEXT("death_back"), TEXT("Death_Respawn"), false, false, false, EMorphRigPriority::Terminal, TEXT("dead_back"));
	AddClip(TEXT("dead_front"), TEXT("Death_Respawn"), true, false, false, EMorphRigPriority::Terminal, nullptr);
	AddClip(TEXT("dead_back"), TEXT("Death_Respawn"), true, false, false, EMorphRigPriority::Terminal, nullptr);
	AddClip(TEXT("respawn"), TEXT("Death_Respawn"), false, false, false, EMorphRigPriority::Terminal, TEXT("idle_combat"));

	// 13. Emotes & Spoken Dialogue Performance (4)
	AddClip(TEXT("greet"), TEXT("Emotes_Dialogue"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"));
	AddClip(TEXT("victory"), TEXT("Emotes_Dialogue"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"));
	AddClip(TEXT("defeat"), TEXT("Emotes_Dialogue"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"));
	AddClip(TEXT("dialogue"), TEXT("Emotes_Dialogue"), false, false, false, EMorphRigPriority::Locomotion, TEXT("idle_combat"));

	// 14. 9-Point Calibrated Aim Offset Grid (9)
	for (const TCHAR* AId : {
		TEXT("aim_down_left"), TEXT("aim_down_center"), TEXT("aim_down_right"),
		TEXT("aim_level_left"), TEXT("aim_level_center"), TEXT("aim_level_right"),
		TEXT("aim_up_left"), TEXT("aim_up_center"), TEXT("aim_up_right") })
	{
		AddClip(AId, TEXT("Aim_Grid"), true, false, false, EMorphRigPriority::Locomotion, nullptr);
	}

	// Wire Aim Offset & Default Idle references on UMorphRigAnimInstance
	if (MorphAnimInstance)
	{
		auto FindSeq = [&](const TCHAR* Name) -> UAnimSequence*
		{
			const int32* Ptr = ClipIndexMap.Find(FName(Name));
			return Ptr ? ClipRegistry[*Ptr].Sequence.Get() : nullptr;
		};
		MorphAnimInstance->IdleSeq = FindSeq(TEXT("idle_combat"));
		MorphAnimInstance->LocoSeqA = FindSeq(TEXT("run_f"));
		MorphAnimInstance->LocoSeqB = FindSeq(TEXT("run_fl"));
		MorphAnimInstance->AimCenter = FindSeq(TEXT("aim_level_center"));
		MorphAnimInstance->AimUp = FindSeq(TEXT("aim_up_center"));
		MorphAnimInstance->AimDown = FindSeq(TEXT("aim_down_center"));
		MorphAnimInstance->AimLeft = FindSeq(TEXT("aim_level_left"));
		MorphAnimInstance->AimRight = FindSeq(TEXT("aim_level_right"));
		MorphAnimInstance->DialogueSeq = FindSeq(TEXT("dialogue"));

		RequestActionById(TEXT("idle_combat"), true);
	}

	UE_LOG(LogMorphRig, Display, TEXT("[MorphRig] Initialized Operative with %d registered clips."), ClipRegistry.Num());
}

bool AMorphRigCharacter::RequestActionById(FName ClipId, bool bForceOverride)
{
	const int32* FoundIdx = ClipIndexMap.Find(ClipId);
	if (!FoundIdx || !MorphAnimInstance)
	{
		return false;
	}
	const FMorphRigClipEntry& Target = ClipRegistry[*FoundIdx];
	if (!Target.Sequence)
	{
		return false;
	}

	// Additive hit reactions layer over current posture without interrupting locomotion or planted feet!
	if (Target.bAdditiveHit && !bForceOverride)
	{
		MorphAnimInstance->PlayAdditiveHit(Target.Sequence, MorphAnimInstance->IdleSeq);
		LogAnimEvent(ClipId, 0.0f);
		return true;
	}

	// Enforce Priority Rules unless explicitly forced by browser/respawn
	if (!bForceOverride)
	{
		// Terminal Dead state only allows respawn!
		if (CurrentPriority == EMorphRigPriority::Terminal &&
			(CurrentActionId == TEXT("death_front") || CurrentActionId == TEXT("death_back") ||
			 CurrentActionId == TEXT("dead_front") || CurrentActionId == TEXT("dead_back")))
		{
			if (ClipId != TEXT("respawn"))
			{
				LogAnimEvent(TEXT("PRIORITY_BLOCKED_BY_DEATH"), ActionElapsed);
				return false;
			}
		}
		// CrowdControl and Knockdown block lower-priority actions
		if (static_cast<uint8>(Target.Priority) < static_cast<uint8>(CurrentPriority))
		{
			LogAnimEvent(TEXT("PRIORITY_BLOCKED"), ActionElapsed);
			return false;
		}
	}

	// Check if moving and Target is upper-body layerable (e.g. ranged_fire, ranged_burst, reload)
	const float HorizSpeed = GetVelocity().Size2D();
	if (Target.bUpperBodyCapable && HorizSpeed > 25.0f && CurrentPriority == EMorphRigPriority::Locomotion && !bForceOverride)
	{
		MorphAnimInstance->PlayUpperBodyAnim(Target.Sequence, 1.0f);
		LogAnimEvent(ClipId, 0.0f);
		return true;
	}

	// Transition Base Layer smoothly from current midpoint (Crossfade = 0.15s)
	MorphAnimInstance->bBlendLocomotion = false;
	MorphAnimInstance->TransitionToBaseAnim(Target.Sequence, Target.bLooping, 0.15f, 0.0);

	CurrentActionId = ClipId;
	CurrentPriority = Target.Priority;
	ActionElapsed = 0.0f;
	LoopAutoAdvanceTimer = 0.0f;
	bComboWindowOpen = false;

	// Setup root-motion dash displacement if dash_f/b/l/r
	bIsDashing = (ClipId == TEXT("dash_f") || ClipId == TEXT("dash_b") || ClipId == TEXT("dash_l") || ClipId == TEXT("dash_r"));
	if (bIsDashing)
	{
		ActiveDashDuration = FMath::Max(0.25f, Target.Sequence->GetPlayLength());
		if (ClipId == TEXT("dash_f")) ActiveDashDirection = GetActorForwardVector();
		else if (ClipId == TEXT("dash_b")) ActiveDashDirection = -GetActorForwardVector();
		else if (ClipId == TEXT("dash_l")) ActiveDashDirection = -GetActorRightVector();
		else ActiveDashDirection = GetActorRightVector();
	}

	// Reset beacon attachment if starting deploy
	if (ClipId == TEXT("deploy") && PropBeaconComp)
	{
		bBeaconDetachedInWorld = false;
		PropBeaconComp->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, TEXT("weapon_l"));
	}

	LogAnimEvent(FName(*FString::Printf(TEXT("STATE_%s"), *ClipId.ToString())), 0.0f);
	return true;
}

void AMorphRigCharacter::InterruptCurrentAction()
{
	const float InterruptedAtSec = ActionElapsed;
	if (CurrentActionId == TEXT("channel_start") || CurrentActionId == TEXT("channel_loop"))
	{
		LogAnimEvent(TEXT("MIDPOINT_INTERRUPT_CHANNEL"), InterruptedAtSec);
		RequestActionById(TEXT("channel_interrupt"), true);
	}
	else if (CurrentActionId == TEXT("uplink_start") || CurrentActionId == TEXT("uplink_loop"))
	{
		LogAnimEvent(TEXT("MIDPOINT_INTERRUPT_UPLINK"), InterruptedAtSec);
		RequestActionById(TEXT("uplink_cancel"), true);
	}
	else if (CurrentActionId == TEXT("charge_start") || CurrentActionId == TEXT("charge_hold"))
	{
		LogAnimEvent(TEXT("MIDPOINT_INTERRUPT_CHARGE"), InterruptedAtSec);
		RequestActionById(TEXT("charge_cancel"), true);
	}
	else if (CurrentPriority == EMorphRigPriority::CombatAbility)
	{
		LogAnimEvent(TEXT("MIDPOINT_CANCEL_TO_IDLE"), InterruptedAtSec);
		RequestActionById(TEXT("idle_combat"), true);
	}
}

void AMorphRigCharacter::TriggerMeleeCombo()
{
	if (CurrentActionId == TEXT("melee_1") && bComboWindowOpen)
	{
		bQueuedNextMelee = true;
		return;
	}
	if (CurrentActionId == TEXT("melee_2") && bComboWindowOpen)
	{
		bQueuedNextMelee = true;
		return;
	}
	MeleeComboStage = 1;
	bQueuedNextMelee = false;
	RequestActionById(TEXT("melee_1"));
}

void AMorphRigCharacter::TriggerRangedSingle()
{
	RequestActionById(TEXT("ranged_fire"));
}

void AMorphRigCharacter::TriggerRangedBurst()
{
	RequestActionById(TEXT("ranged_burst"));
}

void AMorphRigCharacter::TriggerReload()
{
	RequestActionById(TEXT("reload"));
}

void AMorphRigCharacter::ToggleChannel()
{
	if (CurrentActionId == TEXT("channel_start") || CurrentActionId == TEXT("channel_loop"))
	{
		RequestActionById(TEXT("channel_end"), true);
	}
	else
	{
		RequestActionById(TEXT("channel_start"));
	}
}

void AMorphRigCharacter::StartOrReleaseCharge()
{
	if (CurrentActionId == TEXT("charge_start") || CurrentActionId == TEXT("charge_hold"))
	{
		RequestActionById(TEXT("charge_release"), true);
	}
	else
	{
		RequestActionById(TEXT("charge_start"));
	}
}

void AMorphRigCharacter::TriggerDeploy()
{
	RequestActionById(TEXT("deploy"));
}

void AMorphRigCharacter::ToggleUplink()
{
	if (CurrentActionId == TEXT("uplink_start") || CurrentActionId == TEXT("uplink_loop"))
	{
		RequestActionById(TEXT("uplink_end"), true);
	}
	else
	{
		RequestActionById(TEXT("uplink_start"));
	}
}

void AMorphRigCharacter::TriggerDash(FName DashId)
{
	RequestActionById(DashId);
}

void AMorphRigCharacter::TriggerBlinkTeleport()
{
	RequestActionById(TEXT("blink_out"));
}

void AMorphRigCharacter::TriggerHitReaction(FName HitId)
{
	RequestActionById(HitId);
}

void AMorphRigCharacter::TriggerStun()
{
	RequestActionById(TEXT("stun_start"));
}

void AMorphRigCharacter::TriggerKnockdown(bool bFront)
{
	RequestActionById(bFront ? TEXT("knockdown_front") : TEXT("knockup_start"));
}

void AMorphRigCharacter::TriggerSleep()
{
	RequestActionById(TEXT("sleep_start"));
}

void AMorphRigCharacter::TriggerDeath(bool bFront)
{
	RequestActionById(bFront ? TEXT("death_front") : TEXT("death_back"));
}

void AMorphRigCharacter::TriggerRespawn()
{
	RequestActionById(TEXT("respawn"), true);
}

void AMorphRigCharacter::TriggerSpokenDialogue()
{
	bPlayingDialogue = true;
	DialogueTimer = 0.0f;
	if (DialogueAudioComp && DialogueSoundWave)
	{
		DialogueAudioComp->Stop();
		DialogueAudioComp->Play(0.0f);
	}
	if (MorphAnimInstance)
	{
		MorphAnimInstance->DialogueTime = 0.0;
		MorphAnimInstance->DialogueAlpha = 1.0f;
	}
	RequestActionById(TEXT("dialogue"));
	LogAnimEvent(TEXT("DIALOGUE_SPOKEN_START"), 0.0f);
}

void AMorphRigCharacter::SetTeamVariant(int32 NewTeamIndex)
{
	TeamVariantIndex = (NewTeamIndex % 2 + 2) % 2;
	if (!TeamAccentMID && GetMesh() && GetMesh()->GetNumMaterials() > 5)
	{
		TeamAccentMID = GetMesh()->CreateAndSetMaterialInstanceDynamic(5);
	}
	if (TeamAccentMID)
	{
		UTexture2D* BaseTex = (TeamVariantIndex == 0) ? TexTeamA_D : TexTeamB_D;
		UTexture2D* EmissiveTex = (TeamVariantIndex == 0) ? TexTeamA_E : TexTeamB_E;
		if (BaseTex)
		{
			TeamAccentMID->SetTextureParameterValue(TEXT("BaseColorMap"), BaseTex);
		}
		if (EmissiveTex)
		{
			TeamAccentMID->SetTextureParameterValue(TEXT("EmissiveMap"), EmissiveTex);
		}
		const FLinearColor Tint = (TeamVariantIndex == 0)
			? FLinearColor(0.0f, 0.88f, 1.0f, 1.0f)   // Team A Cyan
			: FLinearColor(1.0f, 0.60f, 0.05f, 1.0f); // Team B Amber
		TeamAccentMID->SetVectorParameterValue(TEXT("TeamAccentTint"), Tint);
	}
	LogAnimEvent((TeamVariantIndex == 0) ? TEXT("TEAM_VARIANT_A_CYAN") : TEXT("TEAM_VARIANT_B_AMBER"), ActionElapsed);
}

void AMorphRigCharacter::ToggleTeamVariant()
{
	SetTeamVariant(1 - TeamVariantIndex);
}

void AMorphRigCharacter::SetForcedLODLevel(int32 NewLODIndex)
{
	CurrentLODIndex = FMath::Clamp(NewLODIndex, 0, 2);
	if (GetMesh())
	{
		// In UE USkeletalMeshComponent, ForcedLodModel = 1 is LOD0, 2 is LOD1, 3 is LOD2
		GetMesh()->SetForcedLOD(CurrentLODIndex + 1);
	}
	LogAnimEvent(*FString::Printf(TEXT("LOD_SWITCH_LOD%d"), CurrentLODIndex), ActionElapsed);
}

void AMorphRigCharacter::CycleLODLevel()
{
	SetForcedLODLevel((CurrentLODIndex + 1) % 3);
}

void AMorphRigCharacter::CycleFacialExpression()
{
	static const FName ExprMorphs[] = {
		NAME_None,
		TEXT("expr_focus"),
		TEXT("expr_anger"),
		TEXT("expr_surprise"),
		TEXT("expr_pain"),
		TEXT("expr_joy_confidence"),
		TEXT("expr_concern_sadness")
	};
	static const FName ExprLabels[] = {
		TEXT("Neutral"),
		TEXT("Focus"),
		TEXT("Anger"),
		TEXT("Surprise"),
		TEXT("Pain"),
		TEXT("Joy_Confidence"),
		TEXT("Concern_Sadness")
	};
	ExpressionPresetIndex = (ExpressionPresetIndex + 1) % 7;
	ActiveExpressionName = ExprLabels[ExpressionPresetIndex];
	if (MorphAnimInstance)
	{
		MorphAnimInstance->ActiveExpressionMorph = ExprMorphs[ExpressionPresetIndex];
		MorphAnimInstance->ActiveExpressionWeight = (ExpressionPresetIndex == 0) ? 0.0f : 1.0f;
	}
	LogAnimEvent(*FString::Printf(TEXT("FACE_EXPR_%s"), *ActiveExpressionName.ToString()), ActionElapsed);
}

void AMorphRigCharacter::TriggerManualBlink()
{
	ManualBlinkTimer = 0.22f;
	LogAnimEvent(TEXT("FACE_BLINK"), ActionElapsed);
}

void AMorphRigCharacter::SetPlaybackSpeed(float NewSpeed)
{
	PlaybackSpeed = FMath::Clamp(NewSpeed, 0.5f, 1.5f);
}

void AMorphRigCharacter::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	if (!MorphAnimInstance)
	{
		return;
	}

	const float ScaledDt = DeltaTime * PlaybackSpeed;
	const float PrevElapsed = ActionElapsed;
	ActionElapsed += ScaledDt;

	MorphAnimInstance->AdvanceAnimations(DeltaTime, PlaybackSpeed);

	EvaluateClipMarkers(PrevElapsed, ActionElapsed);
	UpdatePropAttachments(PrevElapsed, ActionElapsed);
	UpdateDashAndBlinkMotion(ScaledDt);
	UpdateLocomotionAndState(ScaledDt);
	UpdateSlopeAndStepGroundIK(DeltaTime);
	UpdateAimAndLookAt(DeltaTime);

	// Update manual blink pulse
	if (ManualBlinkTimer > 0.0f)
	{
		ManualBlinkTimer = FMath::Max(0.0f, ManualBlinkTimer - DeltaTime);
		const float BlinkPhase = FMath::Sin((ManualBlinkTimer / 0.22f) * PI);
		MorphAnimInstance->ManualBlinkL = BlinkPhase;
		MorphAnimInstance->ManualBlinkR = BlinkPhase;
	}
	else
	{
		MorphAnimInstance->ManualBlinkL = 0.0f;
		MorphAnimInstance->ManualBlinkR = 0.0f;
	}

	// Synchronize spoken dialogue overlay
	if (bPlayingDialogue)
	{
		DialogueTimer += ScaledDt;
		MorphAnimInstance->DialogueTime = DialogueTimer;
		if (DialogueTimer >= 14.50f)
		{
			bPlayingDialogue = false;
			MorphAnimInstance->DialogueAlpha = 0.0f;
		}
	}
}

void AMorphRigCharacter::EvaluateClipMarkers(float PrevTime, float CurrTime)
{
	const int32* FoundIdx = ClipIndexMap.Find(CurrentActionId);
	if (!FoundIdx)
	{
		return;
	}
	const FMorphRigClipEntry& Clip = ClipRegistry[*FoundIdx];
	const float ClipLen = Clip.Sequence ? FMath::Max(0.01f, Clip.Sequence->GetPlayLength()) : 1.0f;
	const float WrappedPrev = Clip.bLooping ? FMath::Fmod(PrevTime, ClipLen) : PrevTime;
	const float WrappedCurr = Clip.bLooping ? FMath::Fmod(CurrTime, ClipLen) : CurrTime;

	for (const FMorphRigEventMarker& M : Clip.Markers)
	{
		const bool bTriggered = (WrappedPrev <= WrappedCurr)
			? (WrappedPrev < M.TimeSeconds && WrappedCurr >= M.TimeSeconds)
			: (WrappedPrev < M.TimeSeconds || WrappedCurr >= M.TimeSeconds);
		if (bTriggered)
		{
			LogAnimEvent(M.EventName, WrappedCurr);
			if (M.EventName == TEXT("combo_window_open"))
			{
				bComboWindowOpen = true;
			}
			else if (M.EventName == TEXT("combo_window_close"))
			{
				bComboWindowOpen = false;
				if (bQueuedNextMelee)
				{
					bQueuedNextMelee = false;
					if (CurrentActionId == TEXT("melee_1"))
					{
						RequestActionById(TEXT("melee_2"), true);
						return;
					}
					else if (CurrentActionId == TEXT("melee_2"))
					{
						RequestActionById(TEXT("melee_3"), true);
						return;
					}
				}
			}
			else if (M.EventName == TEXT("blink_vanish") && CurrentActionId == TEXT("blink_out"))
			{
				// Event-driven 400 cm blink displacement (never baked root travel!)
				const FVector Dest = GetActorLocation() + GetActorForwardVector() * 400.0f;
				SetActorLocation(Dest, true);
			}
		}
	}
}

void AMorphRigCharacter::UpdatePropAttachments(float PrevTime, float CurrTime)
{
	if (CurrentActionId == TEXT("reload") && PropCellComp && GetMesh())
	{
		if (PrevTime < 0.40f && CurrTime >= 0.40f)
		{
			PropCellComp->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, TEXT("weapon_l"));
		}
		else if (PrevTime < 1.35f && CurrTime >= 1.35f)
		{
			PropCellComp->AttachToComponent(GetMesh(), FAttachmentTransformRules::SnapToTargetNotIncludingScale, TEXT("cell_socket_r"));
		}
	}
	else if (CurrentActionId == TEXT("deploy") && PropBeaconComp && GetMesh())
	{
		if (PrevTime < 0.72f && CurrTime >= 0.72f && !bBeaconDetachedInWorld)
		{
			bBeaconDetachedInWorld = true;
			PropBeaconComp->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
			DetachedBeaconWorldLoc = GetActorLocation() + GetActorForwardVector() * 85.0f - FVector(0.0f, 0.0f, 86.0f);
			PropBeaconComp->SetWorldLocation(DetachedBeaconWorldLoc);
		}
	}
}

void AMorphRigCharacter::UpdateDashAndBlinkMotion(float DeltaTime)
{
	if (bIsDashing)
	{
		// 200 cm nominal horizontal displacement over ActiveDashDuration
		const float SpeedCmPerSec = 200.0f / FMath::Max(0.20f, ActiveDashDuration);
		AddActorWorldOffset(ActiveDashDirection * (SpeedCmPerSec * DeltaTime), true);
	}
}

void AMorphRigCharacter::UpdateLocomotionAndState(float DeltaTime)
{
	const int32* FoundIdx = ClipIndexMap.Find(CurrentActionId);
	if (!FoundIdx)
	{
		return;
	}
	const FMorphRigClipEntry& Clip = ClipRegistry[*FoundIdx];
	const float ClipLen = Clip.Sequence ? FMath::Max(0.05f, Clip.Sequence->GetPlayLength()) : 1.0f;

	// Advance non-looping one-shots to their NextChainClip upon completion
	if (!Clip.bLooping && ActionElapsed >= ClipLen)
	{
		bIsDashing = false;
		if (!Clip.NextChainClip.IsNone())
		{
			RequestActionById(Clip.NextChainClip, true);
			return;
		}
	}

	// Auto-advance sustained CC/Knockdown loops after a brief hold so interactive & showcase triggers complete full chains
	if (Clip.bLooping && !Clip.NextChainClip.IsNone() &&
		(CurrentPriority == EMorphRigPriority::CrowdControl || CurrentPriority == EMorphRigPriority::Knockdown || CurrentPriority == EMorphRigPriority::JumpAir))
	{
		LoopAutoAdvanceTimer += DeltaTime;
		if (LoopAutoAdvanceTimer >= 1.10f)
		{
			RequestActionById(Clip.NextChainClip, true);
			return;
		}
	}

	// Handle live 8-way locomotion blending when in Locomotion priority and player is moving
	const FVector Vel = GetVelocity();
	const float Speed2D = Vel.Size2D();
	if (CurrentPriority == EMorphRigPriority::Locomotion && Speed2D > 10.0f)
	{
		MorphAnimInstance->bBlendLocomotion = true;
		MorphAnimInstance->LocoSpeedAlpha = FMath::Clamp(Speed2D / 360.0f, 0.0f, 1.0f);

		const FVector LocalDir = GetActorTransform().InverseTransformVectorNoScale(Vel.GetSafeNormal2D());
		const float AngleDeg = FMath::RadiansToDegrees(FMath::Atan2(LocalDir.Y, LocalDir.X)); // [-180, +180]

		// Select primary directional gait clip from 8-way set
		const bool bRun = (Speed2D > 230.0f);
		FName BestDirClip = bRun ? TEXT("run_f") : TEXT("walk_f");
		if (AngleDeg >= -22.5f && AngleDeg < 22.5f) BestDirClip = bRun ? TEXT("run_f") : TEXT("walk_f");
		else if (AngleDeg >= 22.5f && AngleDeg < 67.5f) BestDirClip = bRun ? TEXT("run_fr") : TEXT("walk_fr");
		else if (AngleDeg >= 67.5f && AngleDeg < 112.5f) BestDirClip = bRun ? TEXT("run_r") : TEXT("walk_r");
		else if (AngleDeg >= 112.5f && AngleDeg < 157.5f) BestDirClip = bRun ? TEXT("run_br") : TEXT("walk_br");
		else if (AngleDeg >= -67.5f && AngleDeg < -22.5f) BestDirClip = bRun ? TEXT("run_fl") : TEXT("walk_fl");
		else if (AngleDeg >= -112.5f && AngleDeg < -67.5f) BestDirClip = bRun ? TEXT("run_l") : TEXT("walk_l");
		else if (AngleDeg >= -157.5f && AngleDeg < -112.5f) BestDirClip = bRun ? TEXT("run_bl") : TEXT("walk_bl");
		else BestDirClip = bRun ? TEXT("run_b") : TEXT("walk_b");

		if (const int32* DirIdx = ClipIndexMap.Find(BestDirClip))
		{
			MorphAnimInstance->LocoSeqA = ClipRegistry[*DirIdx].Sequence;
			CurrentActionId = BestDirClip;
		}
	}
	else if (MorphAnimInstance->bBlendLocomotion && Speed2D <= 10.0f)
	{
		MorphAnimInstance->bBlendLocomotion = false;
		RequestActionById(TEXT("idle_combat"), true);
	}
}

void AMorphRigCharacter::UpdateSlopeAndStepGroundIK(float DeltaTime)
{
	if (!GetWorld() || !GetMesh() || !MorphAnimInstance)
	{
		return;
	}

	const float ActorGroundZ = GetActorLocation().Z - GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	const FVector FootLocL = GetMesh()->GetBoneLocation(TEXT("foot_l"));
	const FVector FootLocR = GetMesh()->GetBoneLocation(TEXT("foot_r"));

	auto TraceFoot = [&](const FVector& FootWorldPos, float& OutDz, float& OutPitchDeg)
	{
		FHitResult Hit;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(MorphRigFootIK), false, this);
		const FVector Start(FootWorldPos.X, FootWorldPos.Y, ActorGroundZ + 65.0f);
		const FVector End(FootWorldPos.X, FootWorldPos.Y, ActorGroundZ - 45.0f);
		if (GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params))
		{
			OutDz = FMath::Clamp(Hit.ImpactPoint.Z - ActorGroundZ, -25.0f, 25.0f);
			const FVector LocalNormal = GetActorTransform().InverseTransformVectorNoScale(Hit.ImpactNormal);
			OutPitchDeg = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(LocalNormal.X, LocalNormal.Z)), -25.0f, 25.0f);
		}
		else
		{
			OutDz = 0.0f;
			OutPitchDeg = 0.0f;
		}
	};

	float TargetDzL = 0.0f, TargetPitchL = 0.0f;
	float TargetDzR = 0.0f, TargetPitchR = 0.0f;
	TraceFoot(FootLocL, TargetDzL, TargetPitchL);
	TraceFoot(FootLocR, TargetDzR, TargetPitchR);

	const float TargetPelvisDz = FMath::Min(TargetDzL, TargetDzR);
	MorphAnimInstance->FootOffsetZ_L = FMath::FInterpTo(MorphAnimInstance->FootOffsetZ_L, TargetDzL, DeltaTime, 14.0f);
	MorphAnimInstance->FootOffsetZ_R = FMath::FInterpTo(MorphAnimInstance->FootOffsetZ_R, TargetDzR, DeltaTime, 14.0f);
	MorphAnimInstance->PelvisOffsetZ = FMath::FInterpTo(MorphAnimInstance->PelvisOffsetZ, TargetPelvisDz, DeltaTime, 12.0f);
	MorphAnimInstance->FootPitchDeg_L = FMath::FInterpTo(MorphAnimInstance->FootPitchDeg_L, TargetPitchL, DeltaTime, 14.0f);
	MorphAnimInstance->FootPitchDeg_R = FMath::FInterpTo(MorphAnimInstance->FootPitchDeg_R, TargetPitchR, DeltaTime, 14.0f);
}

void AMorphRigCharacter::UpdateAimAndLookAt(float DeltaTime)
{
	if (!MorphAnimInstance)
	{
		return;
	}
	const FVector ChestWorld = GetActorLocation() + FVector(0.0f, 0.0f, 45.0f);
	const FVector ToTarget = (AimTargetWorldLocation - ChestWorld).GetSafeNormal();
	const FVector LocalTarget = GetActorTransform().InverseTransformVectorNoScale(ToTarget);

	const float TargetYaw = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(LocalTarget.Y, LocalTarget.X)), -75.0f, 75.0f);
	const float TargetPitch = FMath::Clamp(FMath::RadiansToDegrees(FMath::Asin(LocalTarget.Z)), -55.0f, 55.0f);

	MorphAnimInstance->AimYaw = FMath::FInterpTo(MorphAnimInstance->AimYaw, TargetYaw, DeltaTime, 10.0f);
	MorphAnimInstance->AimPitch = FMath::FInterpTo(MorphAnimInstance->AimPitch, TargetPitch, DeltaTime, 10.0f);
	MorphAnimInstance->GazeYawDeg = FMath::Clamp(MorphAnimInstance->AimYaw * 0.35f, -22.0f, 22.0f);
	MorphAnimInstance->GazePitchDeg = FMath::Clamp(MorphAnimInstance->AimPitch * 0.35f, -16.0f, 16.0f);
}

void AMorphRigCharacter::LogAnimEvent(FName EventName, float ClipTime)
{
	if (!bIsPrimaryShowcaseCharacter)
	{
		return;
	}
	const FString Entry = FString::Printf(TEXT("[%.2fs] %s (clip=%s)"), ClipTime, *EventName.ToString(), *CurrentActionId.ToString());
	RecentEventLog.Insert(Entry, 0);
	if (RecentEventLog.Num() > 14)
	{
		RecentEventLog.SetNum(14);
	}
	UE_LOG(LogMorphRig, Display, TEXT("MORPHRIG_EVENT: %s"), *Entry);
}
