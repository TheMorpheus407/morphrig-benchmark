#include "MorphAnimInstance.h"

#include "Animation/AnimSequence.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "Animation/AnimationAsset.h"
#include "Animation/AnimationPoseData.h"
#include "Animation/AnimCurveTypes.h"
#include "AnimationRuntime.h"
#include "BonePose.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Dom/JsonObject.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "TwoBoneIK.h"
#include "MorphRig.h"

namespace MorphAnim
{
static bool IsLoopId(const FName Id)
{
    const FString S = Id.ToString();
    return S == TEXT("idle_relaxed") || S == TEXT("idle_combat") || S == TEXT("idle_wounded") ||
        S == TEXT("sprint_f") || S == TEXT("jump_air") || S == TEXT("fall") ||
        S == TEXT("channel_loop") || S == TEXT("charge_hold") || S == TEXT("uplink_loop") ||
        S == TEXT("stun_loop") || S == TEXT("knockup_air") || S == TEXT("prone_front") ||
        S == TEXT("prone_back") || S == TEXT("sleep_loop") || S.StartsWith(TEXT("walk_")) ||
        S.StartsWith(TEXT("run_"));
}

static bool IsPoseId(const FName Id)
{
    const FString S = Id.ToString();
    return S.StartsWith(TEXT("aim_")) || S == TEXT("dead_front") || S == TEXT("dead_back");
}

static float LengthOf(const FMorphClipPlayer& Player)
{
    return Player.Sequence ? Player.Sequence->GetPlayLength() : 0.0f;
}
}

const TArray<FName>& UMorphAnimInstance::RequiredClipIds()
{
    static const TArray<FName> Ids = []
    {
        TArray<FName> Out;
        const TCHAR* Text = TEXT(
            "idle_relaxed\nidle_combat\nidle_wounded\n"
            "walk_f\nwalk_fl\nwalk_l\nwalk_bl\nwalk_b\nwalk_br\nwalk_r\nwalk_fr\n"
            "run_f\nrun_fl\nrun_l\nrun_bl\nrun_b\nrun_br\nrun_r\nrun_fr\n"
            "sprint_f\nstart_f\nstop_f\nturn_l90\nturn_r90\npivot_l180\npivot_r180\n"
            "jump_start\njump_air\njump_land\nfall\nland_heavy\n"
            "dash_f\ndash_b\ndash_l\ndash_r\nblink_out\nblink_in\n"
            "melee_1\nmelee_2\nmelee_3\nranged_fire\nranged_burst\nreload\n"
            "cast_directional\ncast_ground\ncast_self\n"
            "channel_start\nchannel_loop\nchannel_end\nchannel_interrupt\n"
            "charge_start\ncharge_hold\ncharge_release\ncharge_cancel\ndeploy\n"
            "uplink_start\nuplink_loop\nuplink_end\nuplink_cancel\n"
            "hit_f\nhit_b\nhit_l\nhit_r\n"
            "stun_start\nstun_loop\nstun_end\nknockback\nknockup_start\nknockup_air\n"
            "knockdown_front\nknockdown_back\nprone_front\nprone_back\ngetup_front\ngetup_back\n"
            "sleep_start\nsleep_loop\nsleep_end\ndeath_front\ndeath_back\ndead_front\ndead_back\n"
            "respawn\ngreet\nvictory\ndefeat\ndialogue\n"
            "aim_down_left\naim_down_center\naim_down_right\n"
            "aim_level_left\naim_level_center\naim_level_right\n"
            "aim_up_left\naim_up_center\naim_up_right");
        TArray<FString> Names;
        FString(Text).ParseIntoArrayLines(Names, false);
        for (const FString& Name : Names)
        {
            Out.Add(FName(Name.TrimStartAndEnd()));
        }
        return Out;
    }();
    return Ids;
}

const TArray<FName>& UMorphAnimInstance::FacialMorphNames()
{
    static const TArray<FName> Names = {
        TEXT("JawOpen"), TEXT("Blink.L"), TEXT("Blink.R"), TEXT("Squint.L"), TEXT("Squint.R"),
        TEXT("BrowRaise.L"), TEXT("BrowRaise.R"), TEXT("BrowLower.L"), TEXT("BrowLower.R"),
        TEXT("Cheek.L"), TEXT("Cheek.R"), TEXT("LipClosed"), TEXT("Smile.L"), TEXT("Smile.R"),
        TEXT("Frown.L"), TEXT("Frown.R"), TEXT("MouthWidth"), TEXT("Pucker"), TEXT("Funnel"),
        TEXT("Viseme_MBP"), TEXT("Viseme_FV"), TEXT("Viseme_AA"), TEXT("Viseme_EE"),
        TEXT("Viseme_OO"), TEXT("Viseme_TH"), TEXT("Viseme_CH")
    };
    return Names;
}

FMorphClipMetadata UMorphAnimInstance::MakeDefaultMetadata(const FName Id)
{
    FMorphClipMetadata Meta;
    Meta.Id = Id;
    Meta.AssetPath = FString::Printf(TEXT("/Game/Operative/Animations/%s"), *Id.ToString());
    const FString S = Id.ToString();
    Meta.bLoop = MorphAnim::IsLoopId(Id);
    Meta.bPose = MorphAnim::IsPoseId(Id);
    Meta.bRootMotion = S.StartsWith(TEXT("dash_"));
    if (S.StartsWith(TEXT("hit_")))
    {
        Meta.Form = TEXT("additive");
        Meta.Layer = EMorphClipLayer::Additive;
    }
    else if (Meta.bPose)
    {
        Meta.Form = TEXT("pose");
        Meta.Layer = S.StartsWith(TEXT("aim_")) ? EMorphClipLayer::AimPose : EMorphClipLayer::FullBody;
    }
    else if (S == TEXT("ranged_fire") || S == TEXT("ranged_burst") || S == TEXT("cast_directional"))
    {
        Meta.Layer = EMorphClipLayer::UpperBody;
    }
    else if (Meta.bLoop && (S.StartsWith(TEXT("idle_")) || S.StartsWith(TEXT("walk_")) || S.StartsWith(TEXT("run_")) || S == TEXT("sprint_f")))
    {
        Meta.Layer = EMorphClipLayer::Locomotion;
    }
    if (Meta.bLoop)
    {
        Meta.Form = TEXT("loop");
    }
    return Meta;
}

UMorphAnimInstance::UMorphAnimInstance()
{
    RootMotionMode = ERootMotionMode::RootMotionFromEverything;
}

void UMorphAnimInstance::NativeInitializeAnimation()
{
    Super::NativeInitializeAnimation();
    SetRootMotionMode(ERootMotionMode::RootMotionFromEverything);
    LoadNativeAssets();
    UE_LOG(LogMorphRig, Warning, TEXT("MR_INIT owner=%s"), *GetName());
    RequestClip(TEXT("idle_relaxed"), 0.0f);
}

void UMorphAnimInstance::LoadNativeAssets()
{
    if (bInventoryLoaded)
    {
        return;
    }
    bInventoryLoaded = true;
    for (const FName Id : RequiredClipIds())
    {
        Inventory.Add(Id, MakeDefaultMetadata(Id));
    }
    ReadManifest();
    for (const FName Id : RequiredClipIds())
    {
        FMorphClipMetadata& Meta = Inventory[Id];
        FString ObjectPath = Meta.AssetPath;
        if (!ObjectPath.Contains(TEXT(".")))
        {
            ObjectPath += TEXT(".") + Id.ToString();
        }
        UAnimSequence* Sequence = LoadObject<UAnimSequence>(nullptr, *ObjectPath);
        SequenceAssets.Add(Id, Sequence);
        if (!Sequence)
        {
            UE_LOG(LogMorphRig, Warning, TEXT("MR_ASSET missing clip=%s path=%s"), *Id.ToString(), *ObjectPath);
        }
    }
    GameSnapshot.LoadedClipCount = 0;
    for (const auto& Pair : SequenceAssets)
    {
        GameSnapshot.LoadedClipCount += Pair.Value ? 1 : 0;
    }
}

void UMorphAnimInstance::ReadManifest()
{
    const FString Path = FPaths::ProjectContentDir() / TEXT("Operative/animation_manifest.json");
    FString Json;
    if (!FFileHelper::LoadFileToString(Json, *Path))
    {
        UE_LOG(LogMorphRig, Warning, TEXT("MR_ASSET manifest unavailable path=%s; native inventory fallback active"), *Path);
        return;
    }

    TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Json);
    TSharedPtr<FJsonValue> Root;
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        LastError = TEXT("Manifest parse failed");
        return;
    }

    TArray<TSharedPtr<FJsonValue>> Entries;
    if (Root->Type == EJson::Array)
    {
        Entries = Root->AsArray();
    }
    else if (Root->Type == EJson::Object)
    {
        const TSharedPtr<FJsonObject> Object = Root->AsObject();
        for (const TCHAR* Field : { TEXT("animations"), TEXT("clips"), TEXT("entries"), TEXT("items") })
        {
            if (Object->HasField(Field))
            {
                Entries = Object->GetArrayField(Field);
                break;
            }
        }
    }

    for (const TSharedPtr<FJsonValue>& Value : Entries)
    {
        if (!Value.IsValid() || Value->Type != EJson::Object)
        {
            continue;
        }
        const TSharedPtr<FJsonObject> Entry = Value->AsObject();
        const FName Id(*Entry->GetStringField(TEXT("id")));
        if (!Inventory.Contains(Id))
        {
            continue;
        }
        FMorphClipMetadata& Meta = Inventory[Id];
        Entry->TryGetStringField(TEXT("form"), Meta.Form);
        Entry->TryGetStringField(TEXT("unreal_asset"), Meta.AssetPath);
        Entry->TryGetBoolField(TEXT("loop"), Meta.bLoop);
        Entry->TryGetNumberField(TEXT("duration_seconds"), Meta.Duration);
        Meta.bPose = Meta.Form == TEXT("pose");
        Meta.bRootMotion = Entry->GetStringField(TEXT("root_motion_policy")) == TEXT("root_motion");
        const TArray<TSharedPtr<FJsonValue>>* Events = nullptr;
        if (Entry->TryGetArrayField(TEXT("events"), Events) && Events)
        {
            Meta.EventCount = Events->Num();
        }
        const FString Layer = Entry->GetStringField(TEXT("layer"));
        if (Layer.Contains(TEXT("upper_body")) && !Layer.Contains(TEXT("additive")))
        {
            Meta.Layer = Meta.bPose ? EMorphClipLayer::AimPose : EMorphClipLayer::UpperBody;
        }
        else if (Layer.Contains(TEXT("additive")))
        {
            Meta.Layer = EMorphClipLayer::Additive;
        }
        else if (Layer.Contains(TEXT("locomotion")))
        {
            Meta.Layer = EMorphClipLayer::Locomotion;
        }
    }
    bManifestLoaded = true;
}

bool UMorphAnimInstance::RequestClip(const FName Id, const float Fade, const FName NextId, const bool bHold)
{
    if (!SequenceAssets.FindRef(Id))
    {
        LastError = FName(*FString::Printf(TEXT("Missing clip %s"), *Id.ToString()));
        return false;
    }
    const FMorphClipMetadata& Meta = Inventory[Id];
    FMorphPlayCommand Command;
    Command.Id = Id;
    Command.NextId = NextId;
    Command.Fade = FMath::Max(0.0f, Fade);
    Command.Layer = EMorphClipLayer::FullBody;
    Command.bHold = bHold || Meta.bPose;
    QueueCommand(Command);
    return true;
}

bool UMorphAnimInstance::RequestUpperClip(const FName Id, const float Fade)
{
    if (!SequenceAssets.FindRef(Id))
    {
        LastError = FName(*FString::Printf(TEXT("Missing upper clip %s"), *Id.ToString()));
        return false;
    }
    FMorphPlayCommand Command;
    Command.Id = Id;
    Command.Fade = FMath::Max(0.0f, Fade);
    Command.Layer = EMorphClipLayer::UpperBody;
    QueueCommand(Command);
    return true;
}

bool UMorphAnimInstance::RequestHit(const FName Id)
{
    if (!SequenceAssets.FindRef(Id))
    {
        return false;
    }
    FMorphPlayCommand Command;
    Command.Id = Id;
    Command.Fade = 0.055f;
    Command.Layer = EMorphClipLayer::Additive;
    QueueCommand(Command);
    return true;
}

void UMorphAnimInstance::StopUpper(const float Fade)
{
    FMorphPlayCommand Command;
    Command.Layer = EMorphClipLayer::UpperBody;
    Command.Fade = Fade;
    QueueCommand(Command);
}

void UMorphAnimInstance::QueueCommand(const FMorphPlayCommand& Command)
{
    FScopeLock Lock(&RuntimeLock);
    PendingCommands.Add(Command);
}

void UMorphAnimInstance::SetPlaybackRate(const float Rate)
{
    FScopeLock Lock(&RuntimeLock);
    PendingActionRate = FMath::Clamp(Rate, 0.5f, 1.5f);
}

void UMorphAnimInstance::SetLocomotionRate(const float Rate)
{
    FScopeLock Lock(&RuntimeLock);
    PendingLocomotionRate = FMath::Clamp(Rate, 0.5f, 1.5f);
}

void UMorphAnimInstance::SetAim(const float Yaw, const float Pitch, const bool bEnabled)
{
    FScopeLock Lock(&RuntimeLock);
    PendingAimYaw = FMath::Clamp(Yaw, -60.0f, 60.0f);
    PendingAimPitch = FMath::Clamp(Pitch, -35.0f, 35.0f);
    bPendingAim = bEnabled;
}

void UMorphAnimInstance::SetStasis(const bool bEnabled)
{
    FScopeLock Lock(&RuntimeLock);
    bPendingStasis = bEnabled;
}

void UMorphAnimInstance::SetGroundData(const FMorphGroundData& Data)
{
    FScopeLock Lock(&RuntimeLock);
    PendingGround = Data;
}

void UMorphAnimInstance::SetCaptureFixedStep(const bool bEnabled)
{
    FScopeLock Lock(&RuntimeLock);
    PendingFixedStepSeconds = bEnabled ? 1.0f / 30.0f : 0.0f;
}

float UMorphAnimInstance::GetCaptureStepSeconds() const
{
    FScopeLock Lock(&RuntimeLock);
    return PendingFixedStepSeconds;
}

void UMorphAnimInstance::SetFaceValue(const FName MorphName, const float Value)
{
    FScopeLock Lock(&RuntimeLock);
    if (!bPendingFaceOverride)
    {
        for (const FName Name : FacialMorphNames())
        {
            PendingFaceValues.FindOrAdd(FName(*Name.ToString().Replace(TEXT("."), TEXT("_")))) = 0.0f;
        }
    }
    bPendingFaceOverride = true;
    const FName NativeMorphName(*MorphName.ToString().Replace(TEXT("."), TEXT("_")));
    PendingFaceValues.FindOrAdd(NativeMorphName) = FMath::Clamp(Value, 0.0f, 1.0f);
}

void UMorphAnimInstance::SetFacePreset(const FName PresetName)
{
    ResetFace();
    const FString Preset = PresetName.ToString();
    auto Set = [this](const FName Name, const float Value) { SetFaceValue(Name, Value); };
    if (Preset == TEXT("joy"))
    {
        Set(TEXT("Smile.L"), .82f); Set(TEXT("Smile.R"), .82f); Set(TEXT("Cheek.L"), .55f); Set(TEXT("Cheek.R"), .55f); Set(TEXT("BrowRaise.L"), .12f); Set(TEXT("BrowRaise.R"), .12f);
    }
    else if (Preset == TEXT("anger"))
    {
        Set(TEXT("BrowLower.L"), .85f); Set(TEXT("BrowLower.R"), .85f); Set(TEXT("Squint.L"), .5f); Set(TEXT("Squint.R"), .5f); Set(TEXT("Frown.L"), .4f); Set(TEXT("Frown.R"), .4f);
    }
    else if (Preset == TEXT("concern"))
    {
        Set(TEXT("BrowRaise.L"), .38f); Set(TEXT("BrowRaise.R"), .38f); Set(TEXT("BrowLower.L"), .2f); Set(TEXT("BrowLower.R"), .2f); Set(TEXT("Frown.L"), .55f); Set(TEXT("Frown.R"), .55f);
    }
    else if (Preset == TEXT("surprise"))
    {
        Set(TEXT("BrowRaise.L"), 1.f); Set(TEXT("BrowRaise.R"), 1.f); Set(TEXT("JawOpen"), .62f); Set(TEXT("Funnel"), .2f);
    }
    else if (Preset == TEXT("pain"))
    {
        Set(TEXT("Squint.L"), .72f); Set(TEXT("Squint.R"), .72f); Set(TEXT("BrowLower.L"), .5f); Set(TEXT("BrowLower.R"), .5f); Set(TEXT("Frown.L"), .55f); Set(TEXT("Frown.R"), .55f); Set(TEXT("JawOpen"), .24f);
    }
    else if (Preset == TEXT("focus"))
    {
        Set(TEXT("Squint.L"), .28f); Set(TEXT("Squint.R"), .28f); Set(TEXT("BrowLower.L"), .3f); Set(TEXT("BrowLower.R"), .3f); Set(TEXT("LipClosed"), .35f);
    }
}

void UMorphAnimInstance::ResetFace()
{
    FScopeLock Lock(&RuntimeLock);
    bPendingFaceOverride = true;
    for (const FName Name : FacialMorphNames())
    {
        PendingFaceValues.FindOrAdd(FName(*Name.ToString().Replace(TEXT("."), TEXT("_")))) = 0.0f;
    }
}

void UMorphAnimInstance::ClearFaceOverrides()
{
    FScopeLock Lock(&RuntimeLock);
    bPendingFaceOverride = false;
    PendingFaceValues.Empty();
}

void UMorphAnimInstance::SetEyeLook(const float LeftYaw, const float LeftPitch, const float RightYaw, const float RightPitch)
{
    FScopeLock Lock(&RuntimeLock);
    PendingEyeLeftYaw = FMath::Clamp(LeftYaw, -25.0f, 25.0f);
    PendingEyeLeftPitch = FMath::Clamp(LeftPitch, -18.0f, 18.0f);
    PendingEyeRightYaw = FMath::Clamp(RightYaw, -25.0f, 25.0f);
    PendingEyeRightPitch = FMath::Clamp(RightPitch, -18.0f, 18.0f);
}

void UMorphAnimInstance::ResetRuntime()
{
    FScopeLock Lock(&RuntimeLock);
    PendingCommands.Empty();
    PendingEvents.Empty();
    bResetRequested = true;
    PendingActionRate = PendingLocomotionRate = 1.0f;
    bPendingAim = bPendingStasis = false;
    PendingAimYaw = PendingAimPitch = 0.0f;
    PendingGround = FMorphGroundData();
    PendingFaceValues.Empty();
    bPendingFaceOverride = false;
}

FMorphAnimSnapshot UMorphAnimInstance::GetSnapshot() const
{
    FScopeLock Lock(&RuntimeLock);
    FMorphAnimSnapshot Snapshot = GameSnapshot;
    Snapshot.bGroundError = Snapshot.GroundErrorCount > 0;
    return Snapshot;
}

UAnimSequence* UMorphAnimInstance::GetSequence(const FName Id) const
{
    return SequenceAssets.FindRef(Id);
}

FString UMorphAnimInstance::GetLastError() const
{
    FScopeLock Lock(&RuntimeLock);
    return LastError.ToString();
}

void UMorphAnimInstance::NativeUpdateAnimation(const float DeltaSeconds)
{
    Super::NativeUpdateAnimation(DeltaSeconds);
    TArray<FMorphRuntimeEvent> Events;
    {
        FScopeLock Lock(&RuntimeLock);
        Events = MoveTemp(PendingEvents);
        PendingEvents.Empty();
    }
    for (const FMorphRuntimeEvent& Event : Events)
    {
        GameSnapshot.LastEvent = Event.EventName;
        OnMorphEvent.Broadcast(Event);
    }
}

void UMorphAnimInstance::PushRuntimeEvent(const FMorphRuntimeEvent& Event)
{
    FScopeLock Lock(&RuntimeLock);
    PendingEvents.Add(Event);
}

FAnimInstanceProxy* UMorphAnimInstance::CreateAnimInstanceProxy()
{
    return new FMorphRigAnimInstanceProxy(this);
}

FMorphRigAnimInstanceProxy::FMorphRigAnimInstanceProxy(UAnimInstance* InInstance)
    : FAnimInstanceProxy(InInstance)
{
}

void FMorphRigAnimInstanceProxy::Initialize(UAnimInstance* InAnimInstance)
{
    FAnimInstanceProxy::Initialize(InAnimInstance);
}

void FMorphRigAnimInstanceProxy::InitializeObjects(UAnimInstance* InAnimInstance)
{
    FAnimInstanceProxy::InitializeObjects(InAnimInstance);
    UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(InAnimInstance);
    if (!Owner)
    {
        return;
    }
    if (Sequences.IsEmpty())
    {
        for (const auto& Pair : Owner->SequenceAssets)
        {
            Sequences.Add(Pair.Key, Pair.Value.Get());
        }
    }
    if (Inventory.IsEmpty())
    {
        Inventory = Owner->Inventory;
    }
}

void FMorphRigAnimInstanceProxy::ClearObjects()
{
    FAnimInstanceProxy::ClearObjects();
}

void FMorphRigAnimInstanceProxy::AddReferencedObjects(UAnimInstance* InAnimInstance, FReferenceCollector& Collector)
{
    FAnimInstanceProxy::AddReferencedObjects(InAnimInstance, Collector);
    for (auto& Pair : Sequences)
    {
        Collector.AddReferencedObject(Pair.Value);
    }
    for (FMorphClipPlayer* Player : { &Main, &Previous, &Upper, &UpperPrevious, &Hit })
    {
        Collector.AddReferencedObject(Player->Sequence);
    }
}

void FMorphRigAnimInstanceProxy::PreUpdate(UAnimInstance* InAnimInstance, const float DeltaSeconds)
{
    FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
    UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(InAnimInstance);
    if (!Owner)
    {
        return;
    }
    TArray<FMorphPlayCommand> Commands;
    {
        FScopeLock Lock(&Owner->RuntimeLock);
        Commands = MoveTemp(Owner->PendingCommands);
        Owner->PendingCommands.Empty();
        ActionRate = Owner->PendingActionRate;
        LocomotionRate = Owner->PendingLocomotionRate;
        FixedStepSeconds = Owner->PendingFixedStepSeconds;
        Ground = Owner->PendingGround;
        FaceValues = Owner->PendingFaceValues;
        bFaceOverride = Owner->bPendingFaceOverride;
        EyeLeft = FVector2D(Owner->PendingEyeLeftYaw, Owner->PendingEyeLeftPitch);
        EyeRight = FVector2D(Owner->PendingEyeRightYaw, Owner->PendingEyeRightPitch);
        if (Owner->bResetRequested)
        {
            Main.Reset(); Previous.Reset(); Upper.Reset(); UpperPrevious.Reset(); Hit.Reset();
            AimWeight = 0.0f;
            RuntimeSeconds = 0.0;
            Owner->GameSnapshot.bGroundError = false;
            Owner->bResetRequested = false;
        }
        if (!bStasis)
        {
            AimYaw = Owner->PendingAimYaw;
            AimPitch = Owner->PendingAimPitch;
            bAimEnabled = Owner->bPendingAim;
        }
        bStasis = Owner->bPendingStasis;
    }
    for (const FMorphPlayCommand& Command : Commands)
    {
        StartClip(Command);
    }
    if (!Main.bActive)
    {
        UE_LOG(LogMorphRig, Warning, TEXT("MR_FALLBACK_IDLE owner=%s previous=%s"), *Owner->GetName(), *Main.Metadata.Id.ToString());
        FMorphPlayCommand Idle;
        Idle.Id = TEXT("idle_relaxed");
        Idle.Fade = 0.0f;
        Idle.Layer = EMorphClipLayer::FullBody;
        StartClip(Idle);
    }
    {
        FScopeLock Lock(&Owner->RuntimeLock);
        Owner->GameSnapshot.MainClip = Main.Metadata.Id;
        Owner->GameSnapshot.UpperClip = Upper.Metadata.Id;
        Owner->GameSnapshot.AdditiveClip = Hit.Metadata.Id;
        Owner->GameSnapshot.MainTime = Main.Time;
        Owner->GameSnapshot.MainDuration = MorphAnim::LengthOf(Main);
        Owner->GameSnapshot.UpperTime = Upper.Time;
        Owner->GameSnapshot.MainRate = ActionRate * (Main.Metadata.Layer == EMorphClipLayer::Locomotion ? LocomotionRate : 1.0f);
        Owner->GameSnapshot.MainBlend = Main.Blend;
        Owner->GameSnapshot.bMainComplete = Main.bComplete;
        Owner->GameSnapshot.bStasis = bStasis;
        Owner->GameSnapshot.bGroundIK = Ground.bEnabled;
        Owner->GameSnapshot.GroundPelvisOffset = Ground.PelvisOffset;
        Owner->GameSnapshot.GroundFootErrorCm[0] = Owner->GameSnapshot.GroundFootErrorCm[1] = -1.0f;
        Owner->GameSnapshot.GroundFootAngleDeg[0] = Owner->GameSnapshot.GroundFootAngleDeg[1] = -1.0f;
        Owner->GameSnapshot.Traversal = Traversal;
        Owner->GameSnapshot.LoadedClipCount = 0;
        for (const auto& Pair : Sequences)
        {
            Owner->GameSnapshot.LoadedClipCount += Pair.Value != nullptr;
        }
    }
}

void FMorphRigAnimInstanceProxy::StartClip(const FMorphPlayCommand& Command)
{
    if (Command.Layer == EMorphClipLayer::UpperBody)
    {
        UpperPrevious = Upper;
        UpperPrevious.Blend = Upper.bActive ? 1.0f : 0.0f;
        UpperPrevious.BlendDuration = FMath::Max(.01f, Command.Fade);
        Upper.Reset();
        if (Command.Id.IsNone())
        {
            return;
        }
        Upper.Sequence = Sequences.FindRef(Command.Id);
        if (!Upper.Sequence)
        {
            return;
        }
        Upper.Metadata = Inventory.FindRef(Command.Id);
        Upper.NextId = Command.NextId;
        Upper.Blend = Command.Fade > 0.0f ? 0.0f : 1.0f;
        Upper.BlendDuration = FMath::Max(.01f, Command.Fade);
        Upper.bActive = true;
        Upper.bHold = Command.bHold;
        Upper.Activation = NextActivation++;
        for (const FAnimNotifyEvent& Notify : Upper.Sequence->Notifies)
        {
            if (FMath::IsNearlyZero(Notify.GetTriggerTime()))
            {
                FMorphRuntimeEvent Event;
                Event.EventName = Notify.NotifyName.IsNone() && Notify.Notify ? FName(*Notify.Notify->GetNotifyName()) : Notify.NotifyName;
                Event.ClipId = Command.Id;
                Event.ClipTime = 0.0;
                Event.Traversal = ++Traversal;
                Cast<UMorphAnimInstance>(GetAnimInstanceObject())->PushRuntimeEvent(Event);
            }
        }
        return;
    }
    if (Command.Layer == EMorphClipLayer::Additive)
    {
        Hit.Reset();
        Hit.Sequence = Sequences.FindRef(Command.Id);
        if (!Hit.Sequence)
        {
            return;
        }
        Hit.Metadata = Inventory.FindRef(Command.Id);
        Hit.Blend = 0.0f;
        Hit.BlendDuration = .055f;
        Hit.bActive = true;
        Hit.Activation = NextActivation++;
        return;
    }

    if (Inventory.FindRef(Command.Id).Layer == EMorphClipLayer::FullBody)
    {
        Hit.Reset();
    }
    Previous = Main;
    Previous.Blend = Main.bActive ? 1.0f : 0.0f;
    Previous.NextId = NAME_None;
    Main.Reset();
    Main.Sequence = Sequences.FindRef(Command.Id);
    if (!Main.Sequence)
    {
        Main = Previous;
        Previous.Reset();
        return;
    }
    Main.Metadata = Inventory.FindRef(Command.Id);
    Main.NextId = Command.NextId;
    Main.Blend = Command.Fade > 0.0f && Previous.bActive ? 0.0f : 1.0f;
    Main.BlendDuration = FMath::Max(.01f, Command.Fade);
    Main.bActive = true;
    Main.bHold = Command.bHold;
    Main.Activation = NextActivation++;
    UE_LOG(LogMorphRig, Warning, TEXT("MR_START_CLIP command=%s metadata=%s length=%.6f loop=%d"), *Command.Id.ToString(), *Main.Metadata.Id.ToString(), Main.Sequence->GetPlayLength(), Main.Metadata.bLoop);
    for (const FAnimNotifyEvent& Notify : Main.Sequence->Notifies)
    {
        if (FMath::IsNearlyZero(Notify.GetTriggerTime()))
        {
            FMorphRuntimeEvent Event;
            Event.EventName = Notify.NotifyName.IsNone() && Notify.Notify ? FName(*Notify.Notify->GetNotifyName()) : Notify.NotifyName;
            Event.ClipId = Command.Id;
            Event.ClipTime = 0.0;
            Event.Traversal = ++Traversal;
            Cast<UMorphAnimInstance>(GetAnimInstanceObject())->PushRuntimeEvent(Event);
        }
    }
}

void FMorphRigAnimInstanceProxy::AdvancePlayer(FMorphClipPlayer& Player, const float DeltaSeconds, const float Rate, const bool bRootMotion)
{
    if (!Player.bActive || !Player.Sequence || Player.bComplete || Player.bHold || Player.Metadata.bPose || bStasis)
    {
        return;
    }
    const float Length = Player.Sequence->GetPlayLength();
    if (Length <= KINDA_SMALL_NUMBER)
    {
        Player.bComplete = !Player.Metadata.bLoop;
        return;
    }
    const float PreviousTime = static_cast<float>(Player.Time);
    const float MoveDelta = DeltaSeconds * Rate * Player.RateMultiplier * Player.Sequence->RateScale;
    float NewTime = PreviousTime;
    FAnimationRuntime::AdvanceTime(Player.Metadata.bLoop, MoveDelta, NewTime, Length);
    Player.PreviousTime = Player.Time;
    Player.Time = NewTime;
    Player.DeltaTimeRecord.Set(PreviousTime, MoveDelta);
    const bool bWrapped = Player.Metadata.bLoop && MoveDelta > 0.0f && NewTime < PreviousTime;
    if (Player.Metadata.Id == TEXT("walk_f"))
    {
        UE_LOG(LogMorphRig, Warning, TEXT("MR_LOOP prev=%.5f next=%.5f length=%.5f loop=%d wrapped=%d dt=%.5f rate=%.5f"), PreviousTime, NewTime, Length, Player.Metadata.bLoop, bWrapped, MoveDelta, Rate * Player.RateMultiplier * Player.Sequence->RateScale);
    }
    if (bWrapped)
    {
        ++Player.LoopIndex;
    }

    if (bRootMotion && GetRootMotionMode() == ERootMotionMode::RootMotionFromEverything && Player.Sequence->bEnableRootMotion && MoveDelta != 0.0f)
    {
        const FTransform Start = Player.Sequence->ExtractRootTrackTransform(FAnimExtractContext(PreviousTime, true), nullptr);
        const FTransform End = Player.Sequence->ExtractRootTrackTransform(FAnimExtractContext(NewTime, true), nullptr);
        const FVector RootTranslation = End.GetTranslation() - Start.GetTranslation();
        if (Player.Metadata.Id.ToString().StartsWith(TEXT("dash_")))
        {
            UE_LOG(LogMorphRig, Warning, TEXT("MR_ROOT_DELTA clip=%s time=%.4f dt=%.5f mode=%d enabled=%d delta=%s basis_yaw=0"), *Player.Metadata.Id.ToString(), PreviousTime, MoveDelta, static_cast<int32>(GetRootMotionMode()), Player.Sequence->bEnableRootMotion, *RootTranslation.ToString());
        }
        const FTransform RootDelta(RootTranslation);
        GetExtractedRootMotion().AccumulateWithBlend(RootDelta, Player.Blend);
    }
    if (&Player == &Main || &Player == &Upper || &Player == &Hit)
    {
        EmitCrossedNotifies(Player, PreviousTime, NewTime, bWrapped);
    }
    if (!Player.Metadata.bLoop && NewTime >= Length - KINDA_SMALL_NUMBER)
    {
        Player.Time = Length;
        Player.bComplete = true;
    }
}

void FMorphRigAnimInstanceProxy::EmitCrossedNotifies(const FMorphClipPlayer& Player, const double From, const double To, const bool bWrapped)
{
    if (!Player.Sequence || Player.Sequence->Notifies.Num() == 0 || (!bWrapped && To < From))
    {
        return;
    }
    const double Length = Player.Sequence->GetPlayLength();
    auto EmitRange = [&](const double Begin, const double End, const bool bIncludeZero)
    {
        TArray<FAnimNotifyEvent> Ordered = Player.Sequence->Notifies;
        Ordered.Sort([](const FAnimNotifyEvent& A, const FAnimNotifyEvent& B) { return A.GetTriggerTime() < B.GetTriggerTime(); });
        for (const FAnimNotifyEvent& Notify : Ordered)
        {
            const double Time = Notify.GetTriggerTime();
            const bool bAfterBegin = bIncludeZero ? Time >= Begin - 1.e-5 : Time > Begin + 1.e-5;
            if (bAfterBegin && Time <= End + 1.e-5)
            {
                if (Player.Metadata.Id == TEXT("walk_f"))
                {
                    UE_LOG(LogMorphRig, Warning, TEXT("MR_LOOP_EMIT clip=%s event=%s time=%.5f from=%.5f to=%.5f wrapped=%d"), *Player.Metadata.Id.ToString(), *Notify.NotifyName.ToString(), Time, From, To, bWrapped);
                }
                FMorphRuntimeEvent Event;
                Event.EventName = Notify.NotifyName.IsNone() && Notify.Notify ? FName(*Notify.Notify->GetNotifyName()) : Notify.NotifyName;
                Event.ClipId = Player.Metadata.Id;
                Event.ClipTime = Time;
                Event.Traversal = ++Traversal;
                if (UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(GetAnimInstanceObject()))
                {
                    Owner->PushRuntimeEvent(Event);
                }
            }
        }
    };
    if (bWrapped)
    {
        EmitRange(From, Length, false);
        EmitRange(0.0, To, true);
    }
    else
    {
        EmitRange(From, To, false);
    }
}

void FMorphRigAnimInstanceProxy::Update(const float DeltaSeconds)
{
    FAnimInstanceProxy::Update(DeltaSeconds);
    const float StepSeconds = FixedStepSeconds > 0.0f ? FixedStepSeconds : DeltaSeconds;
    if (bStasis)
    {
        return;
    }
    RuntimeSeconds += StepSeconds;
    AimWeight = FMath::FInterpTo(AimWeight, bAimEnabled ? 1.0f : 0.0f, StepSeconds, 12.0f);

    if (Main.bActive)
    {
        const float Rate = ActionRate * (Main.Metadata.Layer == EMorphClipLayer::Locomotion ? LocomotionRate : 1.0f);
        AdvancePlayer(Main, StepSeconds, Rate, true);
        if (Main.Blend < 1.0f)
        {
            Main.Blend = FMath::Min(1.0f, Main.Blend + StepSeconds / Main.BlendDuration);
            Previous.Blend = 1.0f - Main.Blend;
            AdvancePlayer(Previous, StepSeconds, ActionRate, false);
        }
        else
        {
            Previous.Reset();
        }
        if (Main.bComplete && !Main.NextId.IsNone())
        {
            FMorphPlayCommand Next;
            Next.Id = Main.NextId;
            Next.Layer = EMorphClipLayer::FullBody;
            Next.Fade = .12f;
            Next.bHold = Inventory.FindRef(Next.Id).bPose;
            StartClip(Next);
        }
    }
    if (UpperPrevious.bActive)
    {
        UpperPrevious.Blend = FMath::Max(0.0f, UpperPrevious.Blend - StepSeconds / UpperPrevious.BlendDuration);
        AdvancePlayer(UpperPrevious, StepSeconds, ActionRate, false);
        if (UpperPrevious.Blend <= 0.0f)
        {
            UpperPrevious.Reset();
        }
    }
    if (Upper.bActive)
    {
        Upper.Blend = FMath::Min(1.0f, Upper.Blend + StepSeconds / Upper.BlendDuration);
        AdvancePlayer(Upper, StepSeconds, ActionRate, false);
        if (Upper.bComplete)
        {
            UpperPrevious = Upper;
            UpperPrevious.Blend = 1.0f;
            UpperPrevious.BlendDuration = .12f;
            Upper.Reset();
        }
    }
    if (Hit.bActive)
    {
        Hit.Blend = FMath::Min(1.0f, Hit.Blend + StepSeconds / Hit.BlendDuration);
        AdvancePlayer(Hit, StepSeconds, ActionRate, false);
        if (Hit.bComplete)
        {
            Hit.Reset();
        }
    }
}

FCompactPoseBoneIndex FMorphRigAnimInstanceProxy::CompactIndex(const FBoneContainer& Bones, const FName BoneName)
{
    if (!GetSkeleton())
    {
        return FCompactPoseBoneIndex(INDEX_NONE);
    }
    const FName NativeBoneName(*BoneName.ToString().Replace(TEXT("."), TEXT("_")));
    const int32 SkeletonIndex = GetSkeleton()->GetReferenceSkeleton().FindBoneIndex(NativeBoneName);
    return SkeletonIndex == INDEX_NONE ? FCompactPoseBoneIndex(INDEX_NONE) : Bones.GetCompactPoseIndexFromSkeletonPoseIndex(FSkeletonPoseBoneIndex(SkeletonIndex));
}

void FMorphRigAnimInstanceProxy::CacheBones()
{
    FAnimInstanceProxy::CacheBones();
    RebuildBoneWeights(GetRequiredBones());
}

void FMorphRigAnimInstanceProxy::RebuildBoneWeights(const FBoneContainer& Bones)
{
    const int32 NumBones = Bones.GetNumBones();
    UpperBoneWeights.SetNumZeroed(NumBones);
    HitBoneWeights.SetNumZeroed(NumBones);
    AimBoneWeights.SetNumZeroed(NumBones);
    if (!GetSkeleton())
    {
        return;
    }
    const FReferenceSkeleton& Ref = GetSkeleton()->GetReferenceSkeleton();
    auto IsBelow = [&Ref](int32 Index, const FName Ancestor)
    {
        while (Index != INDEX_NONE)
        {
            if (Ref.GetRefBoneInfo()[Index].Name == Ancestor)
            {
                return true;
            }
            Index = Ref.GetParentIndex(Index);
        }
        return false;
    };
    for (int32 Compact = 0; Compact < NumBones; ++Compact)
    {
        const int32 SkeletonIndex = Bones.GetSkeletonPoseIndexFromCompactPoseIndex(FCompactPoseBoneIndex(Compact)).GetInt();
        if (!Ref.GetRefBoneInfo().IsValidIndex(SkeletonIndex))
        {
            continue;
        }
        const FName Name = Ref.GetRefBoneInfo()[SkeletonIndex].Name;
        float LayerWeight = 0.0f;
        if (IsBelow(SkeletonIndex, TEXT("spine_03")) || IsBelow(SkeletonIndex, TEXT("clavicle_L")) || IsBelow(SkeletonIndex, TEXT("clavicle_R"))) LayerWeight = 1.0f;
        else if (Name == TEXT("spine_02")) LayerWeight = .7f;
        else if (Name == TEXT("spine_01")) LayerWeight = .18f;
        UpperBoneWeights[Compact] = LayerWeight;
        AimBoneWeights[Compact] = LayerWeight;
        HitBoneWeights[Compact] = Name == TEXT("spine_01") ? .28f : LayerWeight;
    }
    PelvisIndex = CompactIndex(Bones, TEXT("pelvis"));
    UpperLegIndices[0] = CompactIndex(Bones, TEXT("thigh.L"));
    UpperLegIndices[1] = CompactIndex(Bones, TEXT("thigh.R"));
    LowerLegIndices[0] = CompactIndex(Bones, TEXT("shin.L"));
    LowerLegIndices[1] = CompactIndex(Bones, TEXT("shin.R"));
    FootIndices[0] = CompactIndex(Bones, TEXT("foot.L"));
    FootIndices[1] = CompactIndex(Bones, TEXT("foot.R"));
    EyeIndices[0] = CompactIndex(Bones, TEXT("eye.L"));
    EyeIndices[1] = CompactIndex(Bones, TEXT("eye.R"));
    for (int32 Index = 0; Index < 3; ++Index)
    {
        CableIndices[Index] = CompactIndex(Bones, FName(*FString::Printf(TEXT("cable_%02d"), Index + 1)));
    }
    if (const UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(GetAnimInstanceObject()))
    {
        const USkeletalMeshComponent* Mesh = Owner->GetOwningComponent();
        const USkeletalMesh* Asset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
        if (Asset)
        {
            const FReferenceSkeleton& MeshReference = Asset->GetRefSkeleton();
            TArray<FTransform> RestComponent;
            RestComponent.SetNum(MeshReference.GetNum());
            for (int32 Index = 0; Index < MeshReference.GetNum(); ++Index)
            {
                const int32 Parent = MeshReference.GetParentIndex(Index);
                RestComponent[Index] = Parent == INDEX_NONE ? MeshReference.GetRefBonePose()[Index] : MeshReference.GetRefBonePose()[Index] * RestComponent[Parent];
            }
            for (int32 Leg = 0; Leg < 2; ++Leg)
            {
                const int32 Bone = MeshReference.FindBoneIndex(Leg == 0 ? FName(TEXT("foot_L")) : FName(TEXT("foot_R")));
                if (Bone != INDEX_NONE) RestFootUpLocal[Leg] = RestComponent[Bone].GetRotation().Inverse().RotateVector(FVector::UpVector).GetSafeNormal();
            }
        }
    }
}

void FMorphRigAnimInstanceProxy::SamplePlayer(const FMorphClipPlayer& Player, FPoseContext& OutPose, const bool bFullPose) const
{
    OutPose.ResetToRefPose();
    if (!Player.Sequence)
    {
        return;
    }
    const bool bExtractRoot = Player.Metadata.bRootMotion && GetRootMotionMode() == ERootMotionMode::RootMotionFromEverything;
    const FAnimExtractContext Extract(Player.Time, bExtractRoot, Player.DeltaTimeRecord, Player.Metadata.bLoop);
    FAnimationPoseData OutputData(OutPose);
    Player.Sequence->GetAnimationPose(OutputData, Extract);
    if (bFullPose && Player.Metadata.Layer == EMorphClipLayer::Additive && Player.Sequence->GetAdditiveAnimType() != AAT_None)
    {
        FPoseContext Idle(OutPose);
        FMorphClipPlayer IdlePlayer;
        IdlePlayer.Sequence = Sequences.FindRef(TEXT("idle_relaxed"));
        IdlePlayer.Metadata = Inventory.FindRef(TEXT("idle_relaxed"));
        IdlePlayer.Time = 0.0;
        IdlePlayer.bHold = true;
        SamplePlayer(IdlePlayer, Idle);
        FAnimationPoseData IdleData(Idle);
        FAnimationPoseData AdditiveData(OutPose);
        FAnimationRuntime::AccumulateAdditivePose(IdleData, AdditiveData, 1.0f, Player.Sequence->GetAdditiveAnimType());
        FAnimationRuntime::BlendTwoPosesTogether(IdleData, IdleData, 1.0f, OutputData);
    }
    if (Player.Metadata.Layer == EMorphClipLayer::Additive && Player.Metadata.Id == TEXT("hit_b"))
    {
        auto Scale = [&OutPose](const FCompactPoseBoneIndex& Index) { return OutPose.Pose[Index].GetScale3D().ToString(); };
        UE_LOG(LogMorphRig, Warning, TEXT("MR_HIT_SAMPLE clip=%s full=%d root=%s thigh=%s shin=%s foot=%s"), *Player.Metadata.Id.ToString(), bFullPose, *Scale(FCompactPoseBoneIndex(0)), *Scale(UpperLegIndices[0]), *Scale(LowerLegIndices[0]), *Scale(FootIndices[0]));
    }
    if (Player.Metadata.Layer == EMorphClipLayer::AimPose && Main.Metadata.Id == TEXT("run_fr"))
    {
        UE_LOG(LogMorphRig, Warning, TEXT("MR_AIM_SAMPLE id=%s time=%.6f root=%s"), *Player.Metadata.Id.ToString(), Player.Time, *OutPose.Pose[FCompactPoseBoneIndex(0)].ToString());
    }
}

bool FMorphRigAnimInstanceProxy::Evaluate(FPoseContext& Output)
{
    if (!Main.bActive || !Main.Sequence)
    {
        Output.ResetToRefPose();
        return true;
    }
    FPoseContext Current(Output);
    FPoseContext Old(Output);
    SamplePlayer(Main, Current);
    auto LogPose = [this](const TCHAR* Stage, const FCompactPose& Pose)
    {
        if (Main.Metadata.Id == TEXT("run_fr") && Upper.Metadata.Id == TEXT("ranged_burst"))
        {
            UE_LOG(LogMorphRig, Warning, TEXT("MR_POSE_STAGE stage=%s time=%.6f blend=%.4f aim=%.4f root=%s"), Stage, Main.Time, Main.Blend, AimWeight, *Pose[FCompactPoseBoneIndex(0)].ToString());
        }
    };
    LogPose(TEXT("sample"), Current.Pose);

    FAnimationPoseData CurrentData(Current);
    FAnimationPoseData OutputData(Output);
    if (Previous.bActive && Previous.Sequence && Main.Blend < 1.0f)
    {
        SamplePlayer(Previous, Old);
        FAnimationPoseData OldData(Old);
        FAnimationRuntime::BlendTwoPosesTogether(OldData, CurrentData, 1.0f - Main.Blend, OutputData);
    }
    else
    {
        FAnimationRuntime::BlendTwoPosesTogether(CurrentData, CurrentData, 1.0f, OutputData);
    }

    LogPose(TEXT("main_blend"), Output.Pose);
    if (AimWeight > .001f && AimBoneWeights.Num() == Output.Pose.GetNumBones())
    {
        static const FName AimIds[3][3] = {
            { TEXT("aim_down_left"), TEXT("aim_down_center"), TEXT("aim_down_right") },
            { TEXT("aim_level_left"), TEXT("aim_level_center"), TEXT("aim_level_right") },
            { TEXT("aim_up_left"), TEXT("aim_up_center"), TEXT("aim_up_right") }
        };
        const double X = (60.0 - FMath::Clamp(AimYaw, -60.0f, 60.0f)) / 60.0;
        const double Y = (FMath::Clamp(AimPitch, -35.0f, 35.0f) + 35.0) / 35.0;
        const int32 X0 = FMath::Clamp(FMath::FloorToInt(X), 0, 1);
        const int32 Y0 = FMath::Clamp(FMath::FloorToInt(Y), 0, 1);
        const double X1Weight = FMath::Clamp(X - X0, 0.0, 1.0);
        const double Y1Weight = FMath::Clamp(Y - Y0, 0.0, 1.0);
        FPoseContext Aim(Output);
        FAnimationPoseData AimData(Aim);
        bool bHasAim = false;
        double Accumulated = 0.0;
        for (int32 Row = 0; Row < 2; ++Row)
        {
            for (int32 Column = 0; Column < 2; ++Column)
            {
                const double Weight = (Column ? X1Weight : 1.0 - X1Weight) * (Row ? Y1Weight : 1.0 - Y1Weight);
                if (Weight <= .0001)
                {
                    continue;
                }
                const FName Id = AimIds[Y0 + Row][X0 + Column];
                UAnimSequence* Sequence = Sequences.FindRef(Id);
                if (!Sequence)
                {
                    continue;
                }
                FMorphClipPlayer AimPlayer;
                AimPlayer.Sequence = Sequence;
                AimPlayer.Metadata = Inventory.FindRef(Id);
                AimPlayer.bHold = true;
                FPoseContext Sample(Output);
                SamplePlayer(AimPlayer, Sample);
                FAnimationPoseData SampleData(Sample);
                if (!bHasAim)
                {
                    FAnimationRuntime::BlendTwoPosesTogether(SampleData, SampleData, 1.0f, AimData);
                    Accumulated = Weight;
                    bHasAim = true;
                }
                else
                {
                    const double NewTotal = Accumulated + Weight;
                    FAnimationRuntime::BlendTwoPosesTogetherInPlace(AimData, SampleData, Accumulated / NewTotal);
                    Accumulated = NewTotal;
                }
            }
        }
        if (bHasAim)
        {
            LogPose(TEXT("combined_aim"), Aim.Pose);
            TArray<float> Weights = AimBoneWeights;
            for (float& Weight : Weights) Weight *= AimWeight;
            FPoseContext Base(Output);
        Base = Output;
            FAnimationPoseData BaseData(Base);
            FAnimationRuntime::BlendTwoPosesTogetherPerBone(BaseData, AimData, Weights, OutputData);
        }
    }

    LogPose(TEXT("aim"), Output.Pose);
    auto ApplyUpper = [&](const FMorphClipPlayer& Player, const float Weight)
    {
        if (!Player.bActive || !Player.Sequence || Weight <= .001f || UpperBoneWeights.Num() != Output.Pose.GetNumBones())
        {
            return;
        }
        FPoseContext Base(Output);
        Base = Output;
        FPoseContext Layer(Output);
        SamplePlayer(Player, Layer);
        FAnimationPoseData BaseData(Base);
        FAnimationPoseData LayerData(Layer);
        TArray<float> Weights = UpperBoneWeights;
        for (float& BoneWeight : Weights) BoneWeight *= Weight;
        FAnimationRuntime::BlendTwoPosesTogetherPerBone(BaseData, LayerData, Weights, OutputData);
    };
    ApplyUpper(UpperPrevious, UpperPrevious.Blend);
    ApplyUpper(Upper, Upper.Blend);

    if (Hit.bActive && Hit.Sequence && HitBoneWeights.Num() == Output.Pose.GetNumBones())
    {
        FPoseContext Base(Output);
        Base = Output;
        FPoseContext Additive(Output);
        FPoseContext Applied(Output);
        SamplePlayer(Hit, Additive, false);
        const float Remaining = FMath::Max(0.0f, MorphAnim::LengthOf(Hit) - Hit.Time);
        const float Weight = Hit.Blend * FMath::Clamp(Remaining / .07f, 0.0f, 1.0f);
        FAnimationPoseData BaseData(Base);
        FAnimationPoseData AdditiveData(Additive);
        FAnimationPoseData AppliedData(Applied);
        FAnimationRuntime::BlendTwoPosesTogether(BaseData, BaseData, 1.0f, AppliedData);
        FAnimationRuntime::AccumulateAdditivePose(AppliedData, AdditiveData, Weight, Hit.Sequence->GetAdditiveAnimType());
        TArray<float> Weights = HitBoneWeights;
        for (float& BoneWeight : Weights) BoneWeight *= Hit.Blend;
        FAnimationRuntime::BlendTwoPosesTogetherPerBone(BaseData, AppliedData, Weights, OutputData);
    }

    LogPose(TEXT("layers"), Output.Pose);
    ApplyProceduralBones(Output.Pose);
    ApplyGroundIK(Output.Pose);
    Output.Pose.NormalizeRotations();
    for (int32 Index = 0; Index < Output.Pose.GetNumBones(); ++Index)
    {
        const FTransform& Transform = Output.Pose[FCompactPoseBoneIndex(Index)];
        if (Transform.ContainsNaN() || Transform.GetScale3D().GetMin() < 1.e-8)
        {
            if (UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(GetAnimInstanceObject()))
            {
                FScopeLock Lock(&Owner->RuntimeLock);
                if (Owner->GameSnapshot.PoseErrorCount == 0)
                {
                    UE_LOG(LogMorphRig, Error, TEXT("MR_POSE_INVALID clip=%s upper=%s hit=%s bone=%d transform=%s"), *Main.Metadata.Id.ToString(), *Upper.Metadata.Id.ToString(), *Hit.Metadata.Id.ToString(), Index, *Transform.ToString());
                }
                ++Owner->GameSnapshot.PoseErrorCount;
            }
            break;
        }
    }
    return true;
}

void FMorphRigAnimInstanceProxy::ApplyProceduralBones(FCompactPose& Pose)
{
    auto ApplyEye = [&Pose](const FCompactPoseBoneIndex Index, const FVector2D Eye)
    {
        if (Index.GetInt() == INDEX_NONE || !Pose.IsValidIndex(Index)) return;
        const FQuat Delta = FRotator(Eye.Y, Eye.X, 0.0).Quaternion();
        FQuat Rotation = Delta * Pose[Index].GetRotation();
        Rotation.Normalize();
        Pose[Index].SetRotation(Rotation);
    };
    ApplyEye(EyeIndices[0], EyeLeft);
    ApplyEye(EyeIndices[1], EyeRight);
    for (int32 Index = 0; Index < 3; ++Index)
    {
        const FCompactPoseBoneIndex Bone = CableIndices[Index];
        if (Bone.GetInt() == INDEX_NONE || !Pose.IsValidIndex(Bone)) continue;
        const float Sway = FMath::Clamp(FMath::Sin(RuntimeSeconds * (1.7 + Index * .31) + Index) * (3.0 + Index * 1.5), -10.0, 10.0);
        const FQuat Delta = FRotator(Sway, 0.0, Sway * .35).Quaternion();
        FQuat Rotation = Delta * Pose[Bone].GetRotation();
        Rotation.Normalize();
        Pose[Bone].SetRotation(Rotation);
    }
}

void FMorphRigAnimInstanceProxy::ApplyGroundIK(FCompactPose& Pose)
{
    if (!Ground.bEnabled || PelvisIndex.GetInt() == INDEX_NONE) return;
    auto Flag = [this](const TCHAR* Stage, const int32 Index, const FTransform& Transform, const FVector& Effector)
    {
        if (UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(GetAnimInstanceObject()))
        {
            FScopeLock Lock(&Owner->RuntimeLock);
            if (!Owner->GameSnapshot.bGroundError)
            {
                UE_LOG(LogMorphRig, Error, TEXT("MR_GROUND_INVALID stage=%s clip=%s upper=%s index=%d transform=%s effector=%s"), Stage, *Main.Metadata.Id.ToString(), *Upper.Metadata.Id.ToString(), Index, *Transform.ToString(), *Effector.ToString());
            }
            Owner->GameSnapshot.bGroundError = true;
            ++Owner->GameSnapshot.GroundErrorCount;
        }
    };
    auto ValidBone = [](const FTransform& Transform)
    {
        return !Transform.ContainsNaN() && Transform.GetScale3D().GetMin() > 1.e-8;
    };
    const TArray<FTransform> Original(Pose.GetBones());
    for (int32 Index = 0; Index < Pose.GetNumBones(); ++Index)
    {
        if (!ValidBone(Pose[FCompactPoseBoneIndex(Index)]))
        {
            Flag(TEXT("input"), Index, Pose[FCompactPoseBoneIndex(Index)], FVector::ZeroVector);
            return;
        }
    }
    if (!FMath::IsFinite(Ground.PelvisOffset))
    {
        Flag(TEXT("pelvis"), -1, FTransform::Identity, FVector::ZeroVector);
        return;
    }
    FCSPose<FCompactPose> ComponentPose;
    ComponentPose.InitPose(Pose);
    double RequiredDrop = 0.0;
    for (int32 Leg = 0; Leg < 2; ++Leg)
    {
        if (!Ground.Feet[Leg].bValid || UpperLegIndices[Leg].GetInt() == INDEX_NONE || LowerLegIndices[Leg].GetInt() == INDEX_NONE || FootIndices[Leg].GetInt() == INDEX_NONE) continue;
        const FVector Hip = ComponentPose.GetComponentSpaceTransform(UpperLegIndices[Leg]).GetLocation();
        const FVector Knee = ComponentPose.GetComponentSpaceTransform(LowerLegIndices[Leg]).GetLocation();
        const FVector Foot = ComponentPose.GetComponentSpaceTransform(FootIndices[Leg]).GetLocation();
        const double MaximumReach = (FVector::Distance(Hip, Knee) + FVector::Distance(Knee, Foot)) * .999;
        const double HorizontalSquared = FVector::DistSquared2D(Hip, Ground.Feet[Leg].EffectorComponent);
        const double VerticalReach = FMath::Sqrt(FMath::Max(0.0, MaximumReach * MaximumReach - HorizontalSquared));
        RequiredDrop = FMath::Max(RequiredDrop, Hip.Z - Ground.Feet[Leg].EffectorComponent.Z - VerticalReach);
    }
    Ground.PelvisOffset = -FMath::Clamp(RequiredDrop, 0.0, 20.0);
    if (FMath::Abs(Ground.PelvisOffset) > .01f)
    {
        FTransform Pelvis = ComponentPose.GetComponentSpaceTransform(PelvisIndex);
        Pelvis.AddToTranslation(FVector(0.0, 0.0, Ground.PelvisOffset));
        ComponentPose.SetComponentSpaceTransform(PelvisIndex, Pelvis);
        FCSPose<FCompactPose>::ConvertComponentPosesToLocalPosesSafe(ComponentPose, Pose);
        ComponentPose.InitPose(Pose);
    }
    TArray<FBoneTransform> Adjustments;
    for (int32 Leg = 0; Leg < 2; ++Leg)
    {
        if (!Ground.Feet[Leg].bValid || UpperLegIndices[Leg].GetInt() == INDEX_NONE || LowerLegIndices[Leg].GetInt() == INDEX_NONE || FootIndices[Leg].GetInt() == INDEX_NONE) continue;
        const FVector EffectorTarget = Ground.Feet[Leg].EffectorComponent;
        const FVector NormalTarget = Ground.Feet[Leg].NormalComponent;
        if (EffectorTarget.ContainsNaN() || NormalTarget.ContainsNaN())
        {
            Flag(TEXT("target"), Leg, FTransform::Identity, EffectorTarget);
            return;
        }
        FTransform UpperTransform = ComponentPose.GetComponentSpaceTransform(UpperLegIndices[Leg]);
        FTransform Lower = ComponentPose.GetComponentSpaceTransform(LowerLegIndices[Leg]);
        FTransform Foot = ComponentPose.GetComponentSpaceTransform(FootIndices[Leg]);
        const double UpperLength = FVector::Distance(UpperTransform.GetLocation(), Lower.GetLocation());
        const double LowerLength = FVector::Distance(Lower.GetLocation(), Foot.GetLocation());
        if (!ValidBone(UpperTransform) || !ValidBone(Lower) || !ValidBone(Foot) || UpperLength < .01 || LowerLength < .01)
        {
            UE_LOG(LogMorphRig, Error, TEXT("MR_GROUND_CHAIN clip=%s upper=%s hit=%s upper_len=%.5f lower_len=%.5f upper_scale=%s lower_scale=%s foot_scale=%s"), *Main.Metadata.Id.ToString(), *Upper.Metadata.Id.ToString(), *Hit.Metadata.Id.ToString(), UpperLength, LowerLength, *UpperTransform.GetScale3D().ToString(), *Lower.GetScale3D().ToString(), *Foot.GetScale3D().ToString());
            Flag(TEXT("chain"), Leg, Foot, EffectorTarget);
            return;
        }
        FVector Delta = EffectorTarget - Foot.GetLocation();
        Delta.Z = FMath::Clamp(Delta.Z, -20.0, 20.0);
        FVector Effector = Foot.GetLocation() + Delta;
        const double MinimumReach = FMath::Abs(UpperLength - LowerLength) + .01;
        const double MaximumReach = (UpperLength + LowerLength) * .999;
        const FVector RootToEffector = Effector - UpperTransform.GetLocation();
        const double Distance = RootToEffector.Size();
        if (Distance > MaximumReach || Distance < MinimumReach)
        {
            const FVector Direction = Distance > .001 ? RootToEffector / Distance : (Foot.GetLocation() - UpperTransform.GetLocation()).GetSafeNormal();
            Effector = UpperTransform.GetLocation() + Direction * FMath::Clamp(Distance, MinimumReach, MaximumReach);
        }
        const FVector UpperLocation = UpperTransform.GetLocation();
        const FVector LowerLocation = Lower.GetLocation();
        const FVector FootLocation = Foot.GetLocation();
        const FVector LegDirection = (FootLocation - UpperLocation).GetSafeNormal();
        FVector Bend = LowerLocation - (UpperLocation + LegDirection * UpperLength);
        if (Bend.SizeSquared() < .01)
        {
            Bend = FVector::CrossProduct(LegDirection, FVector::UpVector);
            if (Bend.IsNearlyZero()) Bend = FVector::RightVector;
        }
        const FVector Pole = LowerLocation + Bend.GetSafeNormal() * 5.0;
        FVector SolvedKnee;
        FVector SolvedFoot;
        AnimationCore::SolveTwoBoneIK(UpperLocation, LowerLocation, FootLocation, Pole, Effector, SolvedKnee, SolvedFoot, UpperLength, LowerLength, false, 1.0, 1.15);
        if (SolvedKnee.ContainsNaN() || SolvedFoot.ContainsNaN())
        {
            Flag(TEXT("solve"), Leg, Foot, Effector);
            return;
        }
        if ((SolvedFoot - EffectorTarget).Size() > .5)
        {
            UE_LOG(LogMorphRig, Warning, TEXT("MR_GROUND_MISS clip=%s target=%s solved=%s original=%s hip=%s upper_len=%.3f lower_len=%.3f pelvis=%.3f"), *Main.Metadata.Id.ToString(), *EffectorTarget.ToString(), *SolvedFoot.ToString(), *FootLocation.ToString(), *UpperLocation.ToString(), UpperLength, LowerLength, Ground.PelvisOffset);
        }
        if (GFrameCounter % 30 == 0 && (Main.Metadata.Id == TEXT("walk_f") || Main.Metadata.Id == TEXT("stop_f")))
        {
            UE_LOG(LogMorphRig, Warning, TEXT("MR_GROUND_SOLVE target=%s solved_foot=%s hip=%s knee=%s original_foot=%s upper_len=%.3f lower_len=%.3f pelvis=%.3f"), *Effector.ToString(), *SolvedFoot.ToString(), *UpperLocation.ToString(), *SolvedKnee.ToString(), *FootLocation.ToString(), UpperLength, LowerLength, Ground.PelvisOffset);
        }
        const FQuat UpperRotation = FQuat::FindBetweenNormals((LowerLocation - UpperLocation).GetSafeNormal(), (SolvedKnee - UpperLocation).GetSafeNormal()) * UpperTransform.GetRotation();
        const FQuat LowerRotation = FQuat::FindBetweenNormals((FootLocation - LowerLocation).GetSafeNormal(), (SolvedFoot - SolvedKnee).GetSafeNormal()) * Lower.GetRotation();
        UpperTransform.SetRotation(UpperRotation);
        Lower.SetLocation(SolvedKnee);
        Lower.SetRotation(LowerRotation);
        Foot.SetLocation(SolvedFoot);
        FVector Normal = NormalTarget.GetSafeNormal();
        if (Normal.Z < FMath::Cos(FMath::DegreesToRadians(20.0f))) Normal = FVector::UpVector;
        const FQuat CandidateRotation = Lower.GetRotation() * Original[FootIndices[Leg].GetInt()].GetRotation();
        const FQuat Alignment = FQuat::FindBetweenNormals(CandidateRotation * RestFootUpLocal[Leg], Normal);
        FQuat FootRotation = Alignment * CandidateRotation;
        FootRotation.Normalize();
        Foot.SetRotation(FootRotation);
        Adjustments.Add(FBoneTransform(UpperLegIndices[Leg], UpperTransform));
        Adjustments.Add(FBoneTransform(LowerLegIndices[Leg], Lower));
        Adjustments.Add(FBoneTransform(FootIndices[Leg], Foot));
    }
    Adjustments.Sort([](const FBoneTransform& A, const FBoneTransform& B) { return A.BoneIndex.GetInt() < B.BoneIndex.GetInt(); });
    if (Adjustments.Num()) ComponentPose.LocalBlendCSBoneTransforms(Adjustments, 1.0f);
    if (UMorphAnimInstance* Owner = Cast<UMorphAnimInstance>(GetAnimInstanceObject()))
    {
        FScopeLock Lock(&Owner->RuntimeLock);
        Owner->GameSnapshot.GroundPelvisOffset = Ground.PelvisOffset;
        for (int32 Leg = 0; Leg < 2; ++Leg)
        {
            if (!Ground.Feet[Leg].bValid || FootIndices[Leg].GetInt() == INDEX_NONE) continue;
            const FTransform Foot = ComponentPose.GetComponentSpaceTransform(FootIndices[Leg]);
            Owner->GameSnapshot.GroundFootErrorCm[Leg] = FVector::Distance(Foot.GetLocation(), Ground.Feet[Leg].EffectorComponent);
            const FVector Normal = Ground.Feet[Leg].NormalComponent.GetSafeNormal();
            Owner->GameSnapshot.GroundFootAngleDeg[Leg] = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Foot.GetRotation() * RestFootUpLocal[Leg], Normal), -1.0, 1.0)));
        }
    }
    FCSPose<FCompactPose>::ConvertComponentPosesToLocalPosesSafe(ComponentPose, Pose);
    for (int32 Index = 0; Index < Pose.GetNumBones(); ++Index)
    {
        if (Pose[FCompactPoseBoneIndex(Index)].ContainsNaN())
        {
            Pose[FCompactPoseBoneIndex(Index)] = Original[Index];
            Flag(TEXT("conversion"), Index, Original[Index], FVector::ZeroVector);
            return;
        }
    }
}

void FMorphRigAnimInstanceProxy::UpdateCurvesPostEvaluation(USkeletalMeshComponent* Mesh)
{
    if (bFaceOverride)
    {
        TMap<FName, float>& Curves = GetAnimationCurves(EAnimCurveType::MorphTargetCurve);
        for (const FName Name : UMorphAnimInstance::FacialMorphNames())
        {
            const FName NativeName(*Name.ToString().Replace(TEXT("."), TEXT("_")));
            Curves.FindOrAdd(NativeName) = FaceValues.FindRef(NativeName);
        }
    }
    FAnimInstanceProxy::UpdateCurvesPostEvaluation(Mesh);
}
