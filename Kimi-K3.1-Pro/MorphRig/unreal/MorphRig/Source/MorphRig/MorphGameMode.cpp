#include "MorphGameMode.h"

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "CollisionShape.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/GameUserSettings.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GenericPlatform/GenericPlatformMemory.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "DynamicRHI.h"
#include "RHIGlobals.h"
#include "UnrealClient.h"
#include "MorphCharacter.h"
#include "MorphHUD.h"
#include "MorphRoom.h"
#include "MorphRig.h"
#include "MorphAuditLibrary.h"

AMorphGameMode::AMorphGameMode()
{
    DefaultPawnClass = AMorphCharacter::StaticClass();
    PrimaryActorTick.bCanEverTick = true;
}

void AMorphGameMode::BeginPlay()
{
    Super::BeginPlay();
    Room = GetWorld()->SpawnActor<AMorphRoom>(AMorphRoom::StaticClass(), FTransform::Identity);
    Operative = Cast<AMorphCharacter>(UGameplayStatics::GetPlayerCharacter(this, 0));
    APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0);
    if (!Operative)
    {
        Operative = GetWorld()->SpawnActor<AMorphCharacter>(AMorphCharacter::StaticClass(), FTransform(FVector(-300, 0, 94)));
        if (Controller && Operative) Controller->Possess(Operative);
    }
    if (Operative)
    {
        Operative->SetActorLocation(FVector(-300, 0, 94), false, nullptr, ETeleportType::TeleportPhysics);
        Operative->SetActorRotation(FRotator::ZeroRotator);
        if (Operative->GetMorphAnim())
        {
            Operative->GetMorphAnim()->OnMorphEvent.AddDynamic(this, &AMorphGameMode::HandleAutomationEvent);
            bAutomationEventsBound = true;
        }
    }
    if (Controller)
    {
        ControlPanel = CreateWidget<UMorphHUD>(Controller, UMorphHUD::StaticClass());
        if (ControlPanel)
        {
            ControlPanel->SetOperative(Operative);
            ControlPanel->AddToViewport();
        }
        Controller->bShowMouseCursor = true;
        Controller->SetInputMode(FInputModeGameAndUI());
        if (Operative) Controller->SetViewTarget(Operative);
    }
}

void AMorphGameMode::StartAutomation()
{
    if (!Operative) return;
    const FString CommandLine = FCommandLine::Get();
    if (FParse::Param(*CommandLine, TEXT("MorphVerify"))) Automation = EAutomationMode::Verify;
    else if (FParse::Value(*CommandLine, TEXT("MorphDemo="), CaptureKind) && CaptureKind.Equals(TEXT("states"), ESearchCase::IgnoreCase)) Automation = EAutomationMode::Demo;
    else if (FParse::Value(*CommandLine, TEXT("MorphCapture="), CaptureKind)) Automation = EAutomationMode::Capture;
    else if (FParse::Param(*CommandLine, TEXT("MorphBenchmark"))) Automation = EAutomationMode::Benchmark;
    if (Automation == EAutomationMode::None)
    {
        bAutomationStarted = true;
        return;
    }
    if (!Operative->GetMesh()->GetSkeletalMeshAsset() || !Operative->GetMorphAnim())
    {
        if (AutomationClock >= 10.0f)
        {
            bAutomationStarted = true;
            const FString Path = Automation == EAutomationMode::Capture ? TEXT("MorphCapture/error.txt") : Automation == EAutomationMode::Demo ? TEXT("MorphDemo/error.txt") : Automation == EAutomationMode::Benchmark ? TEXT("MorphBenchmark/error.txt") : TEXT("MorphVerify/error.txt");
            SaveOutput(Path, TEXT("Timed out waiting for the delivered skeletal mesh and native animation instance.\n"));
            FPlatformMisc::RequestExitWithStatus(true, 1);
        }
        return;
    }
    bAutomationStarted = true;
    Operative->SetAutomationDriven(true);
    if (UMorphAnimInstance* Anim = Operative->GetMorphAnim()) Anim->SetCaptureFixedStep(Automation == EAutomationMode::Capture || Automation == EAutomationMode::Demo);
    VerifyStartLocation = Operative->GetActorLocation();
    if ((Automation == EAutomationMode::Demo || Automation == EAutomationMode::Benchmark) && !Operative->GetMesh()->GetSkeletalMeshAsset())
    {
        SaveOutput(Automation == EAutomationMode::Demo ? TEXT("MorphDemo/error.txt") : TEXT("MorphBenchmark/error.txt"), TEXT("Cannot run: /Game/Operative/SK_Operative is not loaded; the delivered character must be rendered.\n"));
        FPlatformMisc::RequestExitWithStatus(true, 1);
        return;
    }
    if (Automation == EAutomationMode::Capture)
    {
        if (!Operative->GetMesh()->GetSkeletalMeshAsset())
        {
            SaveOutput(TEXT("MorphCapture/error.txt"), TEXT("Cannot capture: /Game/Operative/SK_Operative is not loaded.\n"));
            FPlatformMisc::RequestExitWithStatus(true, 1);
            return;
        }
        CaptureKind = CaptureKind.ToLower();
        bNativeProbe = CaptureKind == TEXT("native") || CaptureKind == TEXT("rest");
        CaptureTotalFrames = bNativeProbe ? 1 : CaptureKind == TEXT("turntable") ? 180 : CaptureKind == TEXT("motion") ? 1260 : 480;
        if (CaptureKind != TEXT("turntable") && CaptureKind != TEXT("motion") && !bNativeProbe) CaptureKind = TEXT("face");
        if (ControlPanel) ControlPanel->SetCapturePresentation();
        CaptureCamera = GetWorld()->SpawnActor<ACameraActor>(ACameraActor::StaticClass(), FTransform::Identity);
        if (bNativeProbe)
        {
            NativeProbeActor = GetWorld()->SpawnActor<AActor>(AActor::StaticClass(), Operative->GetActorTransform());
            USceneComponent* ProbeRoot = NewObject<USceneComponent>(NativeProbeActor, TEXT("NativeProbeRoot"));
            NativeProbeActor->SetRootComponent(ProbeRoot);
            ProbeRoot->RegisterComponent();
            NativeProbeMesh = NewObject<USkeletalMeshComponent>(NativeProbeActor, TEXT("NativeProbeMesh"));
            NativeProbeMesh->SetupAttachment(ProbeRoot);
            FString ProbeMeshPath, ProbeClipPath;
            USkeletalMesh* ProbeAsset = FParse::Value(*CommandLine, TEXT("MorphProbeMesh="), ProbeMeshPath) ? LoadObject<USkeletalMesh>(nullptr, *ProbeMeshPath) : Operative->GetMesh()->GetSkeletalMeshAsset();
            UAnimSequence* ProbeSequence = FParse::Value(*CommandLine, TEXT("MorphProbeClip="), ProbeClipPath) ? LoadObject<UAnimSequence>(nullptr, *ProbeClipPath) : Operative->GetMorphAnim()->GetSequence(TEXT("idle_relaxed"));
            float ProbeYaw;
            if (!ProbeAsset || (CaptureKind == TEXT("native") && !ProbeSequence))
            {
                SaveOutput(TEXT("MorphCapture/error.txt"), TEXT("The requested native geometry probe asset could not be loaded.\n"));
                FPlatformMisc::RequestExitWithStatus(true, 1);
                return;
            }
            NativeProbeMesh->SetSkeletalMeshAsset(ProbeAsset);
            NativeProbeMesh->SetRelativeTransform(Operative->GetMesh()->GetRelativeTransform());
            if (FParse::Value(*CommandLine, TEXT("MorphProbeYaw="), ProbeYaw)) NativeProbeMesh->SetRelativeRotation(FRotator(0, ProbeYaw, 0));
            NativeProbeMesh->RegisterComponent();
            NativeProbeMesh->SetAnimInstanceClass(UAnimSingleNodeInstance::StaticClass());
            if (CaptureKind == TEXT("native")) NativeProbeMesh->PlayAnimation(ProbeSequence, true);
            Operative->GetMesh()->SetVisibility(false);
        }
        CaptureCamera->GetCameraComponent()->SetFieldOfView(CaptureKind == TEXT("turntable") ? 65.0f : 60.0f);
        CaptureCamera->GetCameraComponent()->SetAspectRatioAxisConstraint(AspectRatio_MaintainYFOV);
        CaptureCamera->GetCameraComponent()->bOverrideAspectRatioAxisConstraint = true;
        CaptureCamera->GetCameraComponent()->PostProcessSettings.bOverride_MotionBlurAmount = true;
        CaptureCamera->GetCameraComponent()->PostProcessSettings.MotionBlurAmount = 0.0f;
        if (APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0)) Controller->SetViewTargetWithBlend(CaptureCamera);
    }
    else if (Automation == EAutomationMode::Benchmark)
    {
        if (UGameUserSettings* Settings = GEngine->GetGameUserSettings())
        {
            Settings->SetScreenResolution(FIntPoint(1920, 1080));
            Settings->SetFullscreenMode(EWindowMode::Windowed);
            Settings->SetVSyncEnabled(false);
            Settings->SetFrameRateLimit(0.0f);
            Settings->ApplySettings(false);
        }
        GEngine->Exec(GetWorld(), TEXT("stat unit"));
        if (IConsoleManager::Get().FindConsoleVariable(TEXT("r.NGX.DLSSG.Enable"))) GEngine->Exec(GetWorld(), TEXT("r.NGX.DLSSG.Enable 0"));
        if (IConsoleManager::Get().FindConsoleVariable(TEXT("r.FidelityFX.FI.Enabled"))) GEngine->Exec(GetWorld(), TEXT("r.FidelityFX.FI.Enabled 0"));
        Operative->SetCameraMode(EMorphCameraMode::ThirdPerson);
    }
}

void AMorphGameMode::BindAutomationEvents()
{
    if (!bAutomationEventsBound && Operative && Operative->GetMorphAnim())
    {
        Operative->GetMorphAnim()->OnMorphEvent.AddDynamic(this, &AMorphGameMode::HandleAutomationEvent);
        bAutomationEventsBound = true;
    }
}

void AMorphGameMode::Tick(const float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    BindAutomationEvents();
    AutomationClock += DeltaSeconds;
    if (!bAutomationStarted) StartAutomation();
    if (!bAutomationStarted) return;
    switch (Automation)
    {
    case EAutomationMode::Verify: TickVerify(DeltaSeconds); break;
    case EAutomationMode::Demo: TickDemo(DeltaSeconds); break;
    case EAutomationMode::Capture: TickCapture(DeltaSeconds); break;
    case EAutomationMode::Benchmark: TickBenchmark(DeltaSeconds); break;
    default: break;
    }
}

void AMorphGameMode::SetInstanceCount(const int32 Count)
{
    const int32 Desired = Count <= 1 ? 1 : 10;
    if (Desired == 1)
    {
        for (AMorphCharacter* Extra : AdditionalOperatives) if (Extra) Extra->Destroy();
        AdditionalOperatives.Empty();
        return;
    }
    while (AdditionalOperatives.Num() < 9)
    {
        const int32 Index = AdditionalOperatives.Num();
        const float Rows[] = { -220.0f, -80.0f, 170.0f };
        const FVector Location(-320 + (Index % 3) * 140, Rows[Index / 3], 94);
        AMorphCharacter* Extra = GetWorld()->SpawnActor<AMorphCharacter>(AMorphCharacter::StaticClass(), FTransform(Location));
        if (!Extra) break;
        Extra->SetRemotePerformer(true);
        Extra->SetTeam(Index % 2);
        AdditionalOperatives.Add(Extra);
    }
}

void AMorphGameMode::ToggleControlPanel()
{
    if (ControlPanel) ControlPanel->TogglePanel();
}

FString AMorphGameMode::SaveOutput(const FString& RelativePath, const FString& Contents) const
{
    const FString Path = FPaths::ProjectSavedDir() / TEXT("MorphRig") / RelativePath;
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
    if (!FFileHelper::SaveStringToFile(Contents, *Path))
    {
        UE_LOG(LogMorphRig, Error, TEXT("MR_OUTPUT write_failed path=%s"), *Path);
    }
    else
    {
        UE_LOG(LogMorphRig, Log, TEXT("MR_OUTPUT path=%s"), *Path);
    }
    return Path;
}

void AMorphGameMode::HandleAutomationEvent(const FMorphRuntimeEvent& Event)
{
    if (Automation == EAutomationMode::Demo)
    {
        const FMorphAnimSnapshot Snapshot = Operative->GetMorphAnim()->GetSnapshot();
        DemoTrace += FString::Printf(TEXT("MR_EVENT event=%s clip=%s time=%.6f traversal=%d state=%s clip_time=%.4f speed=%.2f\n"), *Event.EventName.ToString(), *Event.ClipId.ToString(), Event.ClipTime, Event.Traversal, *Operative->GetStateName(), Snapshot.MainTime, Snapshot.MainRate);
    }
    if (Automation == EAutomationMode::Verify && VerifyTransition == 3 && Event.ClipId == TEXT("ranged_burst") && Event.EventName == TEXT("MuzzleFire"))
    {
        ++VerifyMuzzleCount;
    }
    if (Automation == EAutomationMode::Verify && VerifyTransition == 4 && Event.ClipId == TEXT("walk_f") && Event.EventName == TEXT("LoopStart"))
    {
        ++VerifyLoopCount;
    }
}

void AMorphGameMode::VerifyCheck(const FString& Name, const bool bPassed, const FString& Details)
{
    VerifyCheckRows.Add(FString::Printf(TEXT("{\"name\":\"%s\",\"passed\":%s,\"details\":\"%s\"}"), *Name, bPassed ? TEXT("true") : TEXT("false"), *Details));
    if (!bPassed) VerifyFailures.Add(Name + (Details.IsEmpty() ? TEXT("") : TEXT(": ") + Details));
    UE_LOG(LogMorphRig, Log, TEXT("MR_VERIFY check=%s result=%s %s"), *Name, bPassed ? TEXT("PASS") : TEXT("FAIL"), *Details);
}

void AMorphGameMode::TickVerify(const float DeltaSeconds)
{
    if (bFinishing) return;
    UMorphAnimInstance* Anim = Operative->GetMorphAnim();
    if (!Anim)
    {
        bFinishing = true;
        SaveOutput(TEXT("MorphVerify/results.json"), TEXT("{\"success\":false,\"required_clips\":96,\"loaded_clips\":0,\"clip_results\":[],\"checks\":[],\"failures\":[\"Native animation instance unavailable; mesh/import required\"]}\n"));
        FPlatformMisc::RequestExitWithStatus(true, 1);
        return;
    }
    const TArray<FName>& Ids = UMorphAnimInstance::RequiredClipIds();
    if (VerifyIndex < Ids.Num())
    {
        const FName Id = Ids[VerifyIndex];
        if (!bPhaseStarted)
        {
            bPhaseStarted = true;
            PhaseClock = 0.0f;
            UAnimSequence* Sequence = Anim->GetSequence(Id);
            const bool bLoaded = Sequence != nullptr;
            const bool bRequested = Operative->RequestClip(Id);
            VerifyClipRows.Add(FString::Printf(TEXT("{\"id\":\"%s\",\"loaded\":%s,\"requested\":%s,\"length\":%.6f,\"notify_count\":%d,\"sampled\":false}"), *Id.ToString(), bLoaded ? TEXT("true") : TEXT("false"), bRequested ? TEXT("true") : TEXT("false"), Sequence ? Sequence->GetPlayLength() : 0.0f, Sequence ? Sequence->Notifies.Num() : 0));
            if (!bLoaded || !bRequested) VerifyFailures.Add(FString::Printf(TEXT("clip %s load/request"), *Id.ToString()));
            return;
        }
        PhaseClock += DeltaSeconds;
        if (PhaseClock >= .055f)
        {
            const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
            const FQuat RootReference = UMorphAuditLibrary::GetMeshBoneRestTransform(Operative->GetMesh()->GetSkeletalMeshAsset(), TEXT("root")).GetRotation();
            const float RootError = FMath::RadiansToDegrees(Operative->GetMesh()->GetBoneTransform(TEXT("root"), RTS_Component).GetRotation().AngularDistance(RootReference));
            const bool bSampled = Snapshot.MainClip == Id && Snapshot.PoseErrorCount == 0 && RootError < 1.0f;
            UE_LOG(LogMorphRig, Warning, TEXT("MR_VERIFY_SAMPLE expected=%s actual=%s time=%.4f complete=%d state=%s automation=%d direct=%d root_error_deg=%.6f"), *Id.ToString(), *Snapshot.MainClip.ToString(), Snapshot.MainTime, Snapshot.bMainComplete, *Operative->GetStateName(), Operative->IsAutomationDriven(), Operative->IsDirectClip(), RootError);
            VerifyClipRows.Last().RemoveFromEnd(TEXT("\"sampled\":false}"));
            VerifyClipRows.Last() += FString::Printf(TEXT("\"sampled\":%s,\"root_orientation_error_deg\":%.6f}"), bSampled ? TEXT("true") : TEXT("false"), RootError);
            if (!bSampled) VerifyFailures.Add(FString::Printf(TEXT("clip %s sampled/root_basis error=%.6fdeg"), *Id.ToString(), RootError));
            ++VerifyIndex;
            bPhaseStarted = false;
            PhaseClock = 0.0f;
        }
        return;
    }

    PhaseClock += DeltaSeconds;
    if (VerifyTransition >= 12)
    {
        TickExtendedVerify();
        return;
    }
    if (!bPhaseStarted)
    {
        bPhaseStarted = true;
        PhaseClock = 0.0f;
        bMidAction = false;
        switch (VerifyTransition)
        {
        case 0: Operative->SetTeam(1); break;
        case 1: Operative->SetLOD(1); break;
        case 2: Anim->SetFacePreset(TEXT("joy")); break;
        case 3:
            VerifyMuzzleCount = 0;
            Operative->ResetShowcase();
            Anim->RequestClip(TEXT("run_fr"), .1f);
            Operative->SetAim(25, 10);
            Operative->RequestRanged(true);
            break;
        case 4:
            VerifyLoopCount = 0;
            Operative->ResetShowcase();
            Anim->RequestClip(TEXT("walk_f"), .05f);
            break;
        case 5: Operative->StartChannel(); break;
        case 6: Operative->StartCharge(); break;
        case 7: Operative->RequestCast(TEXT("cast_ground")); break;
        case 8: Operative->Respawn(); break;
        case 9: Operative->PlayDialogue(); break;
        case 10:
            Operative->ResetShowcase();
            VerifySubstep = 0;
            VerifyStartLocation = Operative->GetActorLocation();
            Operative->RequestDash(TEXT("f"));
            break;
        case 11: Operative->ResetShowcase(); break;
        default: TickExtendedVerify(); return;
        }
        return;
    }

    bool bComplete = false;
    switch (VerifyTransition)
    {
    case 0:
        if (PhaseClock >= .1f) { VerifyCheck(TEXT("team amber and II badge"), Operative->GetTeam() == 1); bComplete = true; }
        break;
    case 1:
        if (PhaseClock >= .15f) { VerifyCheck(TEXT("forced LOD1"), Operative->GetMesh()->GetForcedLOD() == 2); bComplete = true; }
        break;
    case 2:
        if (PhaseClock >= .18f)
        {
            int32 MissingMorphs = 0;
            const USkeletalMesh* Mesh = Operative->GetMesh()->GetSkeletalMeshAsset();
            if (Mesh)
            {
                for (const FName Morph : UMorphAnimInstance::FacialMorphNames()) if (!Mesh->GetMorphTargetIndexMap().Contains(FName(*Morph.ToString().Replace(TEXT("."), TEXT("_"))))) ++MissingMorphs;
            }
            else MissingMorphs = UMorphAnimInstance::FacialMorphNames().Num();
            VerifyCheck(TEXT("26 facial morphs imported"), MissingMorphs == 0, FString::Printf(TEXT("missing=%d"), MissingMorphs));
            const float Smile = Anim->GetAnimationCurves(EAnimCurveType::MorphTargetCurve).FindRef(TEXT("Smile_L"));
            VerifyCheck(TEXT("face preset reaches proxy curves"), Smile > .7f, FString::Printf(TEXT("Smile.L=%.3f"), Smile));
            bComplete = true;
        }
        break;
    case 3:
        if (!bMidAction && PhaseClock >= .25f)
        {
            const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
            VerifyCheck(TEXT("moving aim upper-body burst"), Snapshot.MainClip == TEXT("run_fr") && Snapshot.UpperTime > 0.0);
            bMidAction = true;
        }
        if (PhaseClock >= .78f)
        {
            VerifyCheck(TEXT("MuzzleFire exactly three times"), VerifyMuzzleCount == 3, FString::Printf(TEXT("count=%d"), VerifyMuzzleCount));
            bComplete = true;
        }
        break;
    case 4:
        if (PhaseClock >= 1.36f)
        {
            const float Length = Anim->GetSequence(TEXT("walk_f"))->GetPlayLength();
            const int32 Expected = 1 + FMath::FloorToInt(PhaseClock / FMath::Max(.01f, Length));
            VerifyCheck(TEXT("loop wrap notify once per traversal"), VerifyLoopCount == Expected, FString::Printf(TEXT("count=%d expected=%d length=%.4f phase=%.4f"), VerifyLoopCount, Expected, Length, PhaseClock));
            bComplete = true;
        }
        break;
    case 5:
        if (!bMidAction && PhaseClock >= .27f) { Operative->InterruptChannel(); bMidAction = true; }
        if (PhaseClock >= .53f) { VerifyCheck(TEXT("channel arbitrary interruption"), Anim->GetSnapshot().MainClip == TEXT("channel_interrupt")); bComplete = true; }
        break;
    case 6:
        if (!bMidAction && PhaseClock >= .31f) { Operative->ReleaseCharge(); bMidAction = true; }
        if (PhaseClock >= .58f) { VerifyCheck(TEXT("charge early release"), Anim->GetSnapshot().MainClip == TEXT("charge_release")); bComplete = true; }
        break;
    case 7:
        if (!bMidAction && PhaseClock >= .16f) { Operative->Die(true); Operative->Die(true); bMidAction = true; }
        if (PhaseClock >= .48f) { VerifyCheck(TEXT("death overrides cast and occurs once"), Operative->IsDead() && Anim->GetSnapshot().MainClip == TEXT("death_front")); bComplete = true; }
        break;
    case 8:
        if (PhaseClock >= .35f)
        {
            VerifyCheck(TEXT("respawn restores living and props"), !Operative->IsDead() && Operative->GetPropState() != TEXT("released"));
            Operative->ResetShowcase();
            bComplete = true;
        }
        break;
    case 9:
        if (VerifySubstep == 0 && PhaseClock >= .42f)
        {
            VerifyCheck(TEXT("dialogue actual audio plays"), Operative->IsDialoguePlaying());
            VerifyCheck(TEXT("dialogue body clip synchronized"), Anim->GetSnapshot().MainClip == TEXT("dialogue"));
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && PhaseClock >= 5.0f)
        {
            const FMorphAnimSnapshot Speech = Anim->GetSnapshot();
            VerifyCheck(TEXT("dialogue mid-performance audio synchronized"), Speech.MainClip == TEXT("dialogue") && Speech.MainTime > 4.0f && Operative->IsDialoguePlaying(), FString::Printf(TEXT("clip=%s time=%.4f audio=%d"), *Speech.MainClip.ToString(), Speech.MainTime, Operative->IsDialoguePlaying()));
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= 16.0f)
        {
            VerifyCheck(TEXT("dialogue completes full speech"), Anim->GetSnapshot().MainClip != TEXT("dialogue") && !Operative->IsDialoguePlaying());
            Operative->ResetShowcase();
            bComplete = true;
        }
        break;
    case 10:
        if (PhaseClock >= .9f)
        {
            const FName Directions[] = { TEXT("f"), TEXT("b"), TEXT("l"), TEXT("r") };
            const FVector Expected[] = { FVector(1, 0, 0), FVector(-1, 0, 0), FVector(0, -1, 0), FVector(0, 1, 0) };
            const int32 Index = FMath::Clamp(VerifySubstep, 0, 3);
            const FVector Delta = Operative->GetActorLocation() - VerifyStartLocation;
            const double Forward = Delta.Dot(Expected[Index]);
            const double Orthogonal = (Delta - Expected[Index] * Forward).Size2D();
            VerifyCheck(FString::Printf(TEXT("dash_%s signed capsule root motion"), *Directions[Index].ToString()), Forward > 150.0 && Orthogonal < .5, FString::Printf(TEXT("forward_cm=%.3f orthogonal_cm=%.4f delta=%s"), Forward, Orthogonal, *Delta.ToString()));
            ++VerifySubstep;
            if (VerifySubstep < 4)
            {
                Operative->ResetShowcase();
                VerifyStartLocation = Operative->GetActorLocation();
                Operative->RequestDash(Directions[VerifySubstep]);
                PhaseClock = 0.0f;
            }
            else
            {
                bComplete = true;
            }
        }
        break;
    case 11:
        if (PhaseClock >= .25f)
        {
            VerifyCheck(TEXT("reset restores neutral living"), !Operative->IsDead() && Operative->GetTeam() == 0 && Operative->GetLOD() == 0);
            bComplete = true;
        }
        break;
    }
    if (bComplete)
    {
        ++VerifyTransition;
        bPhaseStarted = false;
        PhaseClock = 0.0f;
    }
}

void AMorphGameMode::CaptureVerificationFrame(const FString& Name)
{
    const FString Directory = FPaths::ProjectSavedDir() / TEXT("MorphRig/MorphVerify");
    IFileManager::Get().MakeDirectory(*Directory, true);
    const APlayerController* Controller = UGameplayStatics::GetPlayerController(this, 0);
    UE_LOG(LogMorphRig, Warning, TEXT("MR_CAMERA_PROBE name=%s mode=%s camera=%s actor=%s viewtarget=%s"), *Name, *Operative->GetCameraModeName(), *Operative->GetShowcaseCamera()->GetComponentTransform().ToString(), *Operative->GetActorTransform().ToString(), Controller && Controller->GetViewTarget() ? *Controller->GetViewTarget()->GetName() : TEXT("None"));
    const FTransform Head = Operative->GetMesh()->GetBoneTransform(TEXT("head"));
    const FVector EyeMid = (Operative->GetMesh()->GetBoneTransform(TEXT("eye_L")).GetLocation() + Operative->GetMesh()->GetBoneTransform(TEXT("eye_R")).GetLocation()) * .5;
    UE_LOG(LogMorphRig, Warning, TEXT("MR_FACE_AXES head=%s eye_delta=%s look_delta=%s mesh_rotation=%s"), *Head.ToString(), *(EyeMid - Head.GetLocation()).ToString(), *(Operative->GetMesh()->GetSocketTransform(TEXT("look_at"), RTS_World).GetLocation() - Head.GetLocation()).ToString(), *Operative->GetMesh()->GetRelativeRotation().ToString());
    FScreenshotRequest::RequestScreenshot(Directory / Name, Name == TEXT("control_panel"), false, false, FIntRect(), true);
}

void AMorphGameMode::TickExtendedVerify()
{
    UMorphAnimInstance* Anim = Operative->GetMorphAnim();
    auto Complete = [this]()
    {
        ++VerifyTransition;
        bPhaseStarted = false;
        bMidAction = false;
        VerifySubstep = 0;
        PhaseClock = 0.0f;
    };
    auto FootMetrics = [Anim]()
    {
        const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
        float Error = 0.0f;
        float Angle = 0.0f;
        int32 Count = 0;
        for (int32 Leg = 0; Leg < 2; ++Leg)
        {
            if (Snapshot.GroundFootErrorCm[Leg] < 0.0f) continue;
            Error = FMath::Max(Error, Snapshot.GroundFootErrorCm[Leg]);
            Angle = FMath::Max(Angle, Snapshot.GroundFootAngleDeg[Leg]);
            ++Count;
        }
        return FVector(Error, Angle, static_cast<double>(Count));
    };
    if (!bPhaseStarted)
    {
        bPhaseStarted = true;
        PhaseClock = 0.0f;
        bMidAction = false;
        VerifySubstep = 0;
        switch (VerifyTransition)
        {
        case 12:
            Operative->ResetShowcase();
            VerifyStartLocation = UMorphAuditLibrary::GetMeshBoneRestTransform(Operative->GetMesh()->GetSkeletalMeshAsset(), TEXT("foot_L")).GetLocation();
            VerifyRateRecord = 0.0;
            Anim->RequestClip(TEXT("run_f"), .08f);
            Operative->ApplyHit(TEXT("b"));
            break;
        case 13:
            Operative->ResetShowcase();
            Anim->RequestClip(TEXT("channel_loop"), .05f);
            Anim->SetPlaybackRate(.5f);
            break;
        case 14:
            Operative->ResetShowcase();
            Operative->StartUplink();
            break;
        case 15:
            Operative->ResetShowcase();
            Operative->SetRooted(true);
            Operative->StartChannel();
            Operative->RequestDash(TEXT("f"));
            Operative->SetLocomotionDrive(150.0f, 0.0f);
            VerifyStartLocation = Operative->GetActorLocation();
            break;
        case 16:
            Operative->ResetShowcase();
            Operative->StartStun();
            break;
        case 17:
            Operative->ResetShowcase();
            Operative->Knockdown(true);
            break;
        case 18:
            Operative->ResetShowcase();
            Operative->SetActorLocation(FVector(-40, -240, 94));
            Operative->SetCameraMode(EMorphCameraMode::Side);
            VerifyStartLocation = Operative->GetActorLocation();
            Operative->SetAutomationDriven(false);
            Operative->SetLocomotionDrive(150.0f, 0.0f);
            break;
        case 19:
            Operative->ResetShowcase();
            Operative->SetActorLocation(FVector(-10, 260, 94));
            Operative->SetCameraMode(EMorphCameraMode::Side);
            VerifyStartLocation = Operative->GetActorLocation();
            Operative->SetAutomationDriven(false);
            Operative->SetLocomotionDrive(100.0f, 0.0f);
            break;
        case 20:
            Operative->ResetShowcase();
            Operative->SetLOD(2);
            SetInstanceCount(10);
            break;
        case 21:
            Operative->ResetShowcase();
            Operative->SetCameraMode(EMorphCameraMode::Face);
            Anim->SetFacePreset(TEXT("neutral"));
            Anim->SetFaceValue(UMorphAnimInstance::FacialMorphNames()[0], .61f);
            Anim->SetEyeLook(0.0f, 0.0f, 0.0f, 0.0f);
            break;
        case 22:
            Operative->ResetShowcase();
            Operative->RequestReload();
            break;
        case 23:
            Operative->ResetShowcase();
            Operative->RequestDeploy();
            break;
        default:
            FinishVerify();
            return;
        }
        return;
    }

    const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
    switch (VerifyTransition)
    {
    case 12:
        for (const FName Bone : { FName(TEXT("foot_L")), FName(TEXT("foot_R")) })
        {
            const float Lift = Operative->GetMesh()->GetBoneTransform(Bone).GetLocation().Z - Operative->GetMesh()->GetComponentLocation().Z - VerifyStartLocation.Z;
            VerifyRateRecord = FMath::Max(VerifyRateRecord, static_cast<double>(Lift));
        }
        if (!bMidAction && PhaseClock >= .14f)
        {
            VerifyCheck(TEXT("additive hit preserves locomotion"), Snapshot.MainClip == TEXT("run_f") && Snapshot.AdditiveClip == TEXT("hit_b") && !Snapshot.bGroundError);
            bMidAction = true;
        }
        if (VerifySubstep == 0 && PhaseClock >= .50f)
        {
            Anim->RequestClip(TEXT("walk_f"), .06f);
            VerifySubstep = 1;
        }
        if (PhaseClock >= .75f)
        {
            VerifyCheck(TEXT("additive crossfade preserves following pose"), Snapshot.MainClip == TEXT("walk_f") && Snapshot.AdditiveClip.IsNone() && Snapshot.PoseErrorCount == 0);
            VerifyCheck(TEXT("ground IK preserves swing foot lift"), VerifyRateRecord > 5.0, FString::Printf(TEXT("max_swing_cm=%.3f"), VerifyRateRecord));
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 13:
        if (VerifySubstep == 0 && PhaseClock >= .25f)
        {
            VerifyRateRecord = Snapshot.MainTime;
            Anim->SetPlaybackRate(1.5f);
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && PhaseClock >= .50f)
        {
            const double Slow = VerifyRateRecord;
            const double Fast = Snapshot.MainTime - VerifyRateRecord;
            VerifyCheck(TEXT("bounded 0.5x and 1.5x action rates"), Slow > .04 && Fast > Slow * 2.2, FString::Printf(TEXT("slow_delta=%.4f fast_delta=%.4f"), Slow, Fast));
            VerifyTimeRecord = Snapshot.MainTime;
            VerifyTraversalRecord = Snapshot.Traversal;
            Operative->SetStasis(true);
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= .78f)
        {
            VerifyCheck(TEXT("stasis freezes pose and events"), Snapshot.bStasis && FMath::Abs(Snapshot.MainTime - VerifyTimeRecord) < .001 && Snapshot.Traversal == VerifyTraversalRecord, FString::Printf(TEXT("time=%.5f traversal=%d"), Snapshot.MainTime, Snapshot.Traversal));
            Operative->SetStasis(false);
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 14:
        if (VerifySubstep == 0 && PhaseClock >= .35f) { Operative->CancelUplink(); VerifySubstep = 1; }
        if (VerifySubstep == 1 && PhaseClock >= .55f)
        {
            VerifyCheck(TEXT("Uplink arbitrary cancellation"), Snapshot.MainClip == TEXT("uplink_cancel"));
            Operative->StartUplink();
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= 2.10f)
        {
            VerifyCheck(TEXT("Uplink sustained loop"), Snapshot.MainClip == TEXT("uplink_loop") && Snapshot.MainTime > .20);
            Operative->FinishUplink();
            VerifySubstep = 3;
        }
        if (VerifySubstep == 3 && PhaseClock >= 2.30f)
        {
            VerifyCheck(TEXT("Uplink explicit finish"), Snapshot.MainClip == TEXT("uplink_end"));
            Operative->StartChannel();
            VerifySubstep = 4;
        }
        if (VerifySubstep == 4 && PhaseClock >= 3.25f)
        {
            VerifyCheck(TEXT("channel sustained loop"), Snapshot.MainClip == TEXT("channel_loop"));
            Operative->FinishChannel();
            VerifySubstep = 5;
        }
        if (VerifySubstep == 5 && PhaseClock >= 3.45f)
        {
            VerifyCheck(TEXT("channel explicit finish"), Snapshot.MainClip == TEXT("channel_end"));
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 15:
        if (VerifySubstep == 0 && PhaseClock >= .22f) { Operative->SetSilenced(true); VerifySubstep = 1; }
        if (VerifySubstep == 1 && PhaseClock >= .43f)
        {
            const float Travel = FVector::Dist2D(VerifyStartLocation, Operative->GetActorLocation());
            VerifyCheck(TEXT("silence interrupts channel and root stops dash"), Operative->IsSilenced() && Operative->IsRooted() && Snapshot.MainClip == TEXT("channel_interrupt") && Travel < .01f);
            Operative->ResetShowcase();
            Operative->SetRooted(true);
            Operative->RequestRanged(false);
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= .63f)
        {
            VerifyCheck(TEXT("root permits eligible upper-body fire"), Operative->IsRooted() && Snapshot.UpperTime > 0.0f);
            Operative->SetDisarmed(true);
            Operative->RequestMelee(1);
            Operative->RequestRanged(true);
            VerifySubstep = 3;
        }
        if (VerifySubstep == 3 && PhaseClock >= .83f)
        {
            VerifyCheck(TEXT("disarm suppresses weapon actions"), Operative->IsDisarmed() && !Snapshot.MainClip.ToString().StartsWith(TEXT("melee_")) && Snapshot.UpperClip != TEXT("ranged_burst"));
            Operative->SetRooted(false);
            Operative->SetLocomotionDrive(150.0f, 0.0f);
            Operative->SetAutomationDriven(false);
            VerifyStartLocation = Operative->GetActorLocation();
            VerifySubstep = 4;
        }
        if (VerifySubstep == 4 && PhaseClock >= 1.25f)
        {
            const float Travel = FVector::Dist2D(VerifyStartLocation, Operative->GetActorLocation());
            VerifyCheck(TEXT("disarm permits ordinary travel"), Operative->IsDisarmed() && Travel > 25.0f && (Snapshot.MainClip.ToString().StartsWith(TEXT("walk_")) || Snapshot.MainClip == TEXT("start_f")), FString::Printf(TEXT("travel_cm=%.3f clip=%s"), Travel, *Snapshot.MainClip.ToString()));
            Operative->SetAutomationDriven(true);
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 16:
        if (VerifySubstep == 0 && PhaseClock >= .24f) { Operative->EndStun(); VerifySubstep = 1; }
        if (VerifySubstep == 1 && PhaseClock >= .44f)
        {
            VerifyCheck(TEXT("stun exit restores action control"), Snapshot.MainClip == TEXT("stun_end") && !Operative->IsDead());
            Operative->RequestJump();
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= .66f) { Operative->ApplyHit(TEXT("f")); Operative->Die(false); VerifySubstep = 3; }
        if (VerifySubstep == 3 && PhaseClock >= .90f)
        {
            VerifyCheck(TEXT("death overrides jump and additive hit once"), Operative->IsDead() && Snapshot.MainClip == TEXT("death_back") && Snapshot.AdditiveClip.IsNone());
            Operative->Respawn();
            VerifySubstep = 4;
        }
        if (VerifySubstep == 4 && PhaseClock >= 1.16f)
        {
            VerifyCheck(TEXT("jump death respawn restores life"), !Operative->IsDead() && Snapshot.MainClip == TEXT("respawn") && Operative->GetPropState() != TEXT("released"));
            Operative->ResetShowcase();
            Operative->Knockup();
            VerifySubstep = 5;
        }
        if (VerifySubstep == 5 && PhaseClock >= 1.52f)
        {
            VerifyCheck(TEXT("knockup is airborne and excludes ground IK"), Snapshot.MainClip == TEXT("knockup_start") && Operative->GetCharacterMovement()->IsFalling() && !Snapshot.bGroundIK);
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 17:
        if (VerifySubstep == 0 && PhaseClock >= 2.50f)
        {
            VerifyCheck(TEXT("front knockdown reaches matching prone"), Snapshot.MainClip == TEXT("prone_front"));
            Operative->GetUp();
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && PhaseClock >= 5.80f)
        {
            VerifyCheck(TEXT("front getup completes"), Operative->GetControlState() == EMorphControlState::Locomotion && Snapshot.MainClip == TEXT("idle_relaxed") && !Operative->IsDead());
            Operative->Knockdown(false);
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= 8.30f)
        {
            VerifyCheck(TEXT("back knockdown reaches matching prone"), Snapshot.MainClip == TEXT("prone_back"));
            Operative->GetUp();
            VerifySubstep = 3;
        }
        if (VerifySubstep == 3 && PhaseClock >= 11.60f)
        {
            VerifyCheck(TEXT("back getup completes"), Operative->GetControlState() == EMorphControlState::Locomotion && Snapshot.MainClip == TEXT("idle_relaxed") && !Operative->IsDead());
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 18:
        if (!bMidAction && PhaseClock >= .45f)
        {
            const FFindFloorResult& Floor = Operative->GetCharacterMovement()->CurrentFloor;
            UE_LOG(LogMorphRig, Warning, TEXT("MR_TERRAIN_MID position=%s velocity=%s forward=%s drive=%.2f/%.2f mode=%d rooted=%d stasis=%d state=%s accel=%s walkable=%d"), *Operative->GetActorLocation().ToString(), *Operative->GetVelocity().ToString(), *Operative->GetActorForwardVector().ToString(), Operative->GetDriveSpeed(), Operative->GetDriveDirection(), static_cast<int32>(Operative->GetCharacterMovement()->MovementMode), Operative->IsRooted(), Operative->IsStasis(), *Operative->GetStateName(), *Operative->GetCharacterMovement()->GetCurrentAcceleration().ToString(), Operative->GetCharacterMovement()->IsWalkable(Floor.HitResult));
            const FVector Start = Operative->GetActorLocation();
            FHitResult Contact;
            const FCollisionQueryParams Params(SCENE_QUERY_STAT(MorphRampProbe), false, Operative);
            const bool bContact = GetWorld()->SweepSingleByChannel(Contact, Start, Start + Operative->GetActorForwardVector() * 40.0, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeCapsule(38.0f, 90.0f), Params);
            const FString Surface = Contact.Component.IsValid() ? Contact.Component->GetName() : TEXT("None");
            const FString Transform = Contact.Component.IsValid() ? Contact.Component->GetComponentTransform().ToString() : TEXT("");
            UE_LOG(LogMorphRig, Warning, TEXT("MR_TERRAIN_BLOCK hit=%d surface=%s normal=%s point=%s start_penetrating=%d location=%s transform=%s"), bContact, *Surface, *Contact.ImpactNormal.ToString(), *Contact.ImpactPoint.ToString(), Contact.bStartPenetrating, *Contact.Location.ToString(), *Transform);
            bMidAction = true;
        }
        if (VerifySubstep == 0 && PhaseClock >= 1.75f)
        {
            const FFindFloorResult& Floor = Operative->GetCharacterMovement()->CurrentFloor;
            const FVector Location = Operative->GetActorLocation();
            VerifyCheck(TEXT("CharacterMovement traverses 20 degree ramp"), Location.X - VerifyStartLocation.X > 130.0 && Location.Z - VerifyStartLocation.Z > 50.0 && Floor.bBlockingHit && Floor.HitResult.ImpactNormal.Z > .90f && Floor.HitResult.ImpactNormal.Z < .98f && !Operative->GetCharacterMovement()->IsFalling(), FString::Printf(TEXT("x=%.2f z=%.2f floor_z=%.2f normal_z=%.5f"), Location.X, Location.Z, Floor.HitResult.ImpactPoint.Z, Floor.HitResult.ImpactNormal.Z));
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && PhaseClock >= 1.90f)
        {
            Operative->StopLocomotionDrive();
            Operative->SetAutomationDriven(true);
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= 2.15f)
        {
            const FVector Metrics = FootMetrics();
            VerifyCheck(TEXT("ramp foot contact and bounded pelvis"), Snapshot.bGroundIK && Metrics.Z >= 1.0 && Metrics.X <= 6.0 && Metrics.Y <= 35.0 && Snapshot.GroundPelvisOffset >= -20.0f && Snapshot.GroundPelvisOffset <= .1f, FString::Printf(TEXT("feet=%d max_error_cm=%.3f max_angle_deg=%.3f pelvis_cm=%.3f"), static_cast<int32>(Metrics.Z), Metrics.X, Metrics.Y, Snapshot.GroundPelvisOffset));
            CaptureVerificationFrame(TEXT("ramp"));
            VerifySubstep = 3;
        }
        if (VerifySubstep == 3 && PhaseClock >= 2.25f)
        {
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 19:
        if (VerifySubstep == 0 && PhaseClock >= 1.55f)
        {
            Operative->StopLocomotionDrive();
            Operative->SetAutomationDriven(true);
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && PhaseClock >= 1.90f)
        {
            const FFindFloorResult& Floor = Operative->GetCharacterMovement()->CurrentFloor;
            const FVector Metrics = FootMetrics();
            const float Rise = Operative->GetActorLocation().Z - VerifyStartLocation.Z;
            VerifyCheck(TEXT("CharacterMovement climbs 20 cm steps"), Floor.bBlockingHit && Floor.HitResult.ImpactPoint.Z >= 70.0 && Rise >= 65.0f && !Operative->GetCharacterMovement()->IsFalling(), FString::Printf(TEXT("rise_cm=%.3f floor_z=%.3f"), Rise, Floor.HitResult.ImpactPoint.Z));
            VerifyCheck(TEXT("step foot contact without ankle inversion"), Metrics.Z >= 1.0 && Metrics.X <= 6.0 && Metrics.Y <= 35.0, FString::Printf(TEXT("feet=%d max_error_cm=%.3f max_angle_deg=%.3f"), static_cast<int32>(Metrics.Z), Metrics.X, Metrics.Y));
            UE_LOG(LogMorphRig, Warning, TEXT("MR_STEP_METRICS left_error=%.3f right_error=%.3f left_angle=%.3f right_angle=%.3f pelvis=%.3f"), Snapshot.GroundFootErrorCm[0], Snapshot.GroundFootErrorCm[1], Snapshot.GroundFootAngleDeg[0], Snapshot.GroundFootAngleDeg[1], Snapshot.GroundPelvisOffset);
            CaptureVerificationFrame(TEXT("steps"));
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && PhaseClock >= 2.00f)
        {
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 20:
        if (PhaseClock >= .40f)
        {
            VerifyCheck(TEXT("forced LOD2"), Operative->GetMesh()->GetForcedLOD() == 3);
            bool bReady = AdditionalOperatives.Num() == 9;
            for (const AMorphCharacter* Extra : AdditionalOperatives)
            {
                bReady = bReady && Extra && Extra->GetMesh()->GetSkeletalMeshAsset() && Extra->GetMorphAnim() && Extra->GetMorphAnim()->GetSnapshot().LoadedClipCount == 96 && Extra->GetMorphAnim()->GetSnapshot().MainTime > 0.0;
            }
            VerifyCheck(TEXT("ten independently animated instances"), bReady, FString::Printf(TEXT("additional_instances=%d"), AdditionalOperatives.Num()));
            SetInstanceCount(1);
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 21:
        if (PhaseClock < .055f) return;
        if (VerifySubstep < UMorphAnimInstance::FacialMorphNames().Num())
        {
            const TArray<FName>& Morphs = UMorphAnimInstance::FacialMorphNames();
            const FName Morph = Morphs[VerifySubstep];
            const FName NativeName(*Morph.ToString().Replace(TEXT("."), TEXT("_")));
            const TMap<FName, float>& Curves = Anim->GetAnimationCurves(EAnimCurveType::MorphTargetCurve);
            const float Actual = Curves.FindRef(NativeName);
            float OtherMaximum = 0.0f;
            for (const FName Other : Morphs)
            {
                if (Other == Morph) continue;
                OtherMaximum = FMath::Max(OtherMaximum, FMath::Abs(Curves.FindRef(FName(*Other.ToString().Replace(TEXT("."), TEXT("_"))))));
            }
            VerifyCheck(FString::Printf(TEXT("facial control %s evaluated independently"), *Morph.ToString()), FMath::Abs(Actual - .61f) < .0001f && OtherMaximum < .0001f, FString::Printf(TEXT("actual=%.5f requested=0.61000 other_max=%.5f"), Actual, OtherMaximum));
            if (VerifySubstep == 1)
            {
                VerifyCheck(TEXT("left blink leaves right eye open"), FMath::Abs(Actual - .61f) < .0001f && Curves.FindRef(TEXT("Blink_R")) < .0001f, FString::Printf(TEXT("left=%.4f right=%.4f"), Actual, Curves.FindRef(TEXT("Blink_R"))));
                CaptureVerificationFrame(TEXT("left_blink"));
            }
            ++VerifySubstep;
            if (VerifySubstep < Morphs.Num())
            {
                Anim->SetFacePreset(TEXT("neutral"));
                Anim->SetFaceValue(Morphs[VerifySubstep], .61f);
                PhaseClock = 0.0f;
                return;
            }
        }
        if (VerifySubstep == 26)
        {
            VerifyEyeReference[0] = Operative->GetMesh()->GetBoneTransform(TEXT("eye_L")).GetRotation();
            VerifyEyeReference[1] = Operative->GetMesh()->GetBoneTransform(TEXT("eye_R")).GetRotation();
            Anim->SetFacePreset(TEXT("neutral"));
            Anim->SetEyeLook(25.0f, -18.0f, -20.0f, 18.0f);
            VerifySubstep = 27;
            PhaseClock = 0.0f;
            return;
        }
        if (VerifySubstep == 27)
        {
            const FQuat Left = Operative->GetMesh()->GetBoneTransform(TEXT("eye_L")).GetRotation();
            const FQuat Right = Operative->GetMesh()->GetBoneTransform(TEXT("eye_R")).GetRotation();
            const float LeftDegrees = FMath::RadiansToDegrees(VerifyEyeReference[0].AngularDistance(Left));
            const float RightDegrees = FMath::RadiansToDegrees(VerifyEyeReference[1].AngularDistance(Right));
            const float DistinctDegrees = FMath::RadiansToDegrees((Left * VerifyEyeReference[0].Inverse()).AngularDistance(Right * VerifyEyeReference[1].Inverse()));
            VerifyCheck(TEXT("independent eye bone rotations"), LeftDegrees > 20.0f && RightDegrees > 20.0f && DistinctDegrees > 5.0f, FString::Printf(TEXT("left_deg=%.3f right_deg=%.3f distinct_deg=%.3f"), LeftDegrees, RightDegrees, DistinctDegrees));
            Anim->SetEyeLook(0.0f, 0.0f, 0.0f, 0.0f);
            VerifySubstep = 28;
            PhaseClock = 0.0f;
            return;
        }
        if (VerifySubstep == 28)
        {
            Operative->ResetShowcase();
            Complete();
        }
        break;
    case 22:
        if (VerifySubstep == 0 && Snapshot.MainClip == TEXT("reload") && Snapshot.MainTime >= .25f)
        {
            VerifyBoneReference[0] = Operative->GetMesh()->GetBoneTransform(TEXT("cell")).GetLocation();
            VerifyBoneReference[1] = Operative->GetMesh()->GetBoneTransform(TEXT("hand_L")).GetLocation();
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && Snapshot.MainClip == TEXT("reload") && Snapshot.MainTime >= 1.10f)
        {
            const FVector Cell = Operative->GetMesh()->GetBoneTransform(TEXT("cell")).GetLocation();
            const FVector Hand = Operative->GetMesh()->GetBoneTransform(TEXT("hand_L")).GetLocation();
            const float CellTravel = FVector::Distance(Cell, VerifyBoneReference[0]);
            const float HandTravel = FVector::Distance(Hand, VerifyBoneReference[1]);
            const float Contact = FVector::Distance(Cell, Hand);
            UE_LOG(LogMorphRig, Warning, TEXT("MR_RELOAD_CONTACT cell=%s hand=%s travel_cm=%.3f/%.3f distance_cm=%.3f"), *Cell.ToString(), *Hand.ToString(), CellTravel, HandTravel, Contact);
            VerifyCheck(TEXT("reload moves cell with supporting hand"), CellTravel > 10.0f && HandTravel > 10.0f && Contact < 10.0f, FString::Printf(TEXT("cell_travel=%.3f hand_travel=%.3f contact_cm=%.3f"), CellTravel, HandTravel, Contact));
            CaptureVerificationFrame(TEXT("reload"));
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && Snapshot.MainClip != TEXT("reload"))
        {
            VerifyCheck(TEXT("reload completes cell seating"), Operative->GetPropState() == TEXT("CellRelease"), Operative->GetPropState());
            Operative->ResetShowcase();
            Complete();
        }
        if (PhaseClock > 3.5f)
        {
            VerifyCheck(TEXT("reload runtime sample timeout"), false, Snapshot.MainClip.ToString());
            Complete();
        }
        break;
    case 23:
        if (VerifySubstep == 0 && Snapshot.MainClip == TEXT("deploy") && Snapshot.MainTime >= .99f)
        {
            const FVector Beacon = Operative->GetMesh()->GetBoneTransform(TEXT("beacon")).GetLocation();
            const FVector Hand = Operative->GetMesh()->GetBoneTransform(TEXT("hand_L")).GetLocation();
            const FVector Finger = Operative->GetMesh()->GetBoneTransform(TEXT("middle_03_L")).GetLocation();
            float FloorHeight = 1000.0f;
            float LowestVertex = 0.0f;
            FHitResult FloorHit;
            FCollisionQueryParams Params(SCENE_QUERY_STAT(MorphDeployContact), false, Operative);
            const bool bHasFloor = Operative->GetWorld()->LineTraceSingleByChannel(FloorHit, Beacon + FVector(0, 0, 15), Beacon - FVector(0, 0, 70), ECC_Visibility, Params);
            if (bHasFloor && UMorphAuditLibrary::GetLowestSkinnedBoneZ(Operative->GetMesh(), TEXT("beacon"), LowestVertex))
            {
                FloorHeight = Operative->GetMesh()->GetComponentTransform().TransformPosition(FVector(0, 0, LowestVertex)).Z - FloorHit.ImpactPoint.Z;
            }
            const float WristDistance = FVector::Distance(Hand, Beacon);
            const float FingerDistance = FVector::Distance(Finger, Beacon);
            const FVector BoneOrigin = Operative->GetMesh()->GetComponentSpaceTransforms()[Operative->GetMesh()->GetBoneIndex(TEXT("beacon"))].GetLocation();
            UE_LOG(LogMorphRig, Warning, TEXT("MR_DEPLOY_GEOMETRY bone_origin=%s socket=%s skin_local_z=%.6f skin_world_z=%.6f hit_z=%.6f hit_component=%s"), *BoneOrigin.ToString(), *Beacon.ToString(), LowestVertex, Operative->GetMesh()->GetComponentLocation().Z + LowestVertex, FloorHit.ImpactPoint.Z, FloorHit.Component.IsValid() ? *FloorHit.Component->GetName() : TEXT("None"));
            UE_LOG(LogMorphRig, Warning, TEXT("MR_DEPLOY_CONTACT beacon=%s hand=%s finger=%s wrist_cm=%.3f finger_cm=%.3f floor_cm=%.3f"), *Beacon.ToString(), *Hand.ToString(), *Finger.ToString(), WristDistance, FingerDistance, FloorHeight);
            VerifyCheck(TEXT("deploy floor and hand contact"), WristDistance < 16.0f && FingerDistance < 8.0f && FMath::Abs(FloorHeight) < .75f, FString::Printf(TEXT("wrist_cm=%.3f finger_cm=%.3f floor_cm=%.3f"), WristDistance, FingerDistance, FloorHeight));
            CaptureVerificationFrame(TEXT("deploy_contact"));
            VerifySubstep = 1;
        }
        if (VerifySubstep == 1 && Snapshot.MainClip == TEXT("deploy") && Snapshot.MainTime >= 1.23f)
        {
            VerifyCheck(TEXT("deploy release detaches authored beacon"), Operative->IsDeployedBeaconVisible() && Operative->GetMesh()->IsBoneHiddenByName(TEXT("beacon")));
            VerifyBoneReference[0] = Operative->GetDeployedBeaconPosition();
            VerifySubstep = 2;
        }
        if (VerifySubstep == 2 && Snapshot.MainClip != TEXT("deploy"))
        {
            const float Drift = FVector::Distance(VerifyBoneReference[0], Operative->GetDeployedBeaconPosition());
            VerifyCheck(TEXT("deployed beacon remains after action"), Operative->IsDeployedBeaconVisible() && Drift < .01f, FString::Printf(TEXT("drift_cm=%.5f"), Drift));
            CaptureVerificationFrame(TEXT("deploy_released"));
            Operative->ResetShowcase();
            Complete();
        }
        if (PhaseClock > 4.5f)
        {
            VerifyCheck(TEXT("deploy runtime sample timeout"), false, Snapshot.MainClip.ToString());
            Complete();
        }
        break;
    default:
        FinishVerify();
        break;
    }
}

void AMorphGameMode::FinishVerify()
{
    if (bFinishing) return;
    bFinishing = true;
    const FMorphAnimSnapshot Snapshot = Operative->GetMorphAnim()->GetSnapshot();
    VerifyCheck(TEXT("finite ground IK evaluation"), !Snapshot.bGroundError && Snapshot.PoseErrorCount == 0, FString::Printf(TEXT("ground_errors=%d pose_errors=%d"), Snapshot.GroundErrorCount, Snapshot.PoseErrorCount));
    const bool bSuccess = VerifyFailures.Num() == 0 && Snapshot.LoadedClipCount == 96 && Operative->GetMorphAnim()->IsManifestLoaded();
    const FString FailureJson = VerifyFailures.Num() ? TEXT("\"") + FString::Join(VerifyFailures, TEXT("\",\"")) + TEXT("\"") : TEXT("");
    const FString Report = FString::Printf(TEXT(
        "{\n\"engine\":\"%s\",\n\"success\":%s,\n\"required_clips\":96,\n\"loaded_clips\":%d,\n\"manifest_loaded\":%s,\n\"clip_results\":[%s],\n\"checks\":[%s],\n\"failures\":[%s]\n}\n"),
        *FEngineVersion::Current().ToString(), bSuccess ? TEXT("true") : TEXT("false"), Snapshot.LoadedClipCount,
        Operative->GetMorphAnim()->IsManifestLoaded() ? TEXT("true") : TEXT("false"),
        *FString::Join(VerifyClipRows, TEXT(",\n")), *FString::Join(VerifyCheckRows, TEXT(",\n")), *FailureJson);
    SaveOutput(TEXT("MorphVerify/results.json"), Report);
    UE_LOG(LogMorphRig, Log, TEXT("MR_VERIFY complete success=%d failures=%d"), bSuccess, VerifyFailures.Num());
    FPlatformMisc::RequestExitWithStatus(true, bSuccess ? 0 : 1);
}

void AMorphGameMode::RunDemoStep(const int32 Step)
{
    UMorphAnimInstance* Anim = Operative->GetMorphAnim();
    const FMorphAnimSnapshot Snapshot = Anim->GetSnapshot();
    UE_LOG(LogMorphRig, Log, TEXT("MR_STATE demo=states step=%d state=%s clip=%s"), Step, *Operative->GetStateName(), *Snapshot.MainClip.ToString());
    DemoTrace += FString::Printf(TEXT("MR_STATE demo_step=%d state=%s clip=%s clip_time=%.4f speed=%.2f\n"), Step, *Operative->GetStateName(), *Snapshot.MainClip.ToString(), Snapshot.MainTime, Snapshot.MainRate);
    switch (Step)
    {
    case 0:
        Operative->ResetShowcase();
        Anim->RequestClip(TEXT("run_fr"));
        Operative->SetAim(25, 10);
        Operative->RequestRanged(true);
        break;
    case 1: Operative->StartChannel(); break;
    case 2: Operative->InterruptChannel(); break;
    case 3: Operative->StartCharge(); break;
    case 4: Operative->ReleaseCharge(); break;
    case 5:
        Operative->ResetShowcase();
        Anim->RequestClip(TEXT("run_l"));
        Operative->SetAim(-20, 5);
        Operative->RequestRanged(false);
        Operative->ApplyHit(TEXT("l"));
        break;
    case 6: Operative->Knockdown(true); break;
    case 7: Operative->GetUp(); break;
    case 8: Operative->StartSleep(); break;
    case 9: Operative->EndSleep(); break;
    case 10: Operative->RequestCast(TEXT("cast_ground")); break;
    case 11: Operative->Die(false); break;
    case 12: Operative->Die(false); break;
    case 13: Operative->Respawn(); break;
    case 14: Operative->ResetShowcase(); Operative->PlayDialogue(); break;
    default: break;
    }
}

void AMorphGameMode::TickDemo(const float)
{
    if (bFinishing) return;
    PhaseClock += 1.0f / 30.0f;
    if (!bMidAction && PhaseClock >= .75f)
    {
        CaptureVerificationFrame(TEXT("control_panel"));
        bMidAction = true;
    }
    static const float StepTimes[] = { 0, 1.2, 2.5, 3.0, 3.45, 4.3, 5.0, 7.5, 8.0, 10.6, 11.5, 12.0, 13.0, 13.2, 16.3 };
    if (DemoStep < UE_ARRAY_COUNT(StepTimes))
    {
        if (PhaseClock >= StepTimes[DemoStep])
        {
            RunDemoStep(DemoStep);
            ++DemoStep;
        }
        return;
    }
    if (PhaseClock >= 32.0f)
    {
        bFinishing = true;
        SaveOutput(TEXT("MorphDemo/states_trace.txt"), DemoTrace);
        FPlatformMisc::RequestExitWithStatus(true, 0);
    }
}

void AMorphGameMode::UpdateCaptureCamera()
{
    if (!CaptureCamera || !Operative) return;
    const FVector Actor = Operative->GetActorLocation();
    FVector Location;
    FVector Focus;
    if (CaptureKind == TEXT("turntable"))
    {
        Location = VerifyStartLocation + FVector(280, -100, 105);
        Focus = VerifyStartLocation + FVector(0, 0, 10);
    }
    else if (CaptureKind == TEXT("motion"))
    {
        if (CaptureFrame < 60)
        {
            Location = Actor + FVector(-750, -600, 1100);
            Focus = Actor + FVector(0, 0, 35);
        }
        else if (CaptureFrame >= 1030 && CaptureFrame < 1090)
        {
            Location = Actor + FVector(190, -280, 130);
            Focus = Actor + FVector(0, 0, -25);
        }
        else if (CaptureFrame >= 970 && CaptureFrame < 1150)
        {
            Location = Actor + FVector(180, -260, 115);
            Focus = Actor + FVector(0, 0, 20);
        }
        else
        {
            Location = Actor + FVector(240, -290, 160);
            Focus = Actor + FVector(0, 0, 15);
        }
    }
    else
    {
        const USkeletalMeshComponent* Mesh = NativeProbeMesh ? NativeProbeMesh : Operative->GetMesh();
        const int32 Head = Mesh->GetBoneIndex(TEXT("head"));
        Focus = Head == INDEX_NONE ? Actor + FVector(0, 0, 65) : Mesh->GetBoneTransform(Head).GetLocation() + Operative->GetActorForwardVector() * 5.0 + FVector(0, 0, 14);
        Location = Focus + Operative->GetActorForwardVector() * 52.0 - Operative->GetActorRightVector() * 3.0 + FVector(0, 0, 2);
    }
    CaptureCamera->SetActorLocationAndRotation(Location, (Focus - Location).Rotation());
}

void AMorphGameMode::TickCapture(const float DeltaSeconds)
{
    if (bFinishing)
    {
        PhaseClock += 1.0f / 30.0f;
        if (PhaseClock >= 10.0f / 30.0f)
        {
            const FString Report = FString::Printf(TEXT("{\"kind\":\"%s\",\"fps\":30,\"frames\":%d,\"engine\":\"%s\",\"mesh_loaded\":true,\"directory\":\"%s\"}\n"), *CaptureKind, CaptureTotalFrames, *FEngineVersion::Current().ToString(), *(FPaths::ProjectSavedDir() / TEXT("MorphRig/MorphCapture") / CaptureKind));
            SaveOutput(TEXT("MorphCapture/") + CaptureKind + TEXT("/capture.json"), Report);
            FPlatformMisc::RequestExitWithStatus(true, 0);
        }
        return;
    }
    if (PhaseClock < 10.0f)
    {
        PhaseClock += 1.0f;
        UpdateCaptureCamera();
        return;
    }
    UMorphAnimInstance* Anim = Operative->GetMorphAnim();
    if (CaptureFrame >= CaptureTotalFrames)
    {
        bFinishing = true;
        PhaseClock = 0.0f;
        return;
    }
    if (CaptureFrame == 0)
    {
        const USkeletalMeshComponent* Mesh = Operative->GetMesh();
        const FVector Head = Mesh->GetBoneTransform(TEXT("head")).GetLocation();
        const FVector Eyes = (Mesh->GetBoneTransform(TEXT("eye_L")).GetLocation() + Mesh->GetBoneTransform(TEXT("eye_R")).GetLocation()) * .5;
        const FVector Face = Operative->GetActorTransform().InverseTransformPosition(Eyes) - Operative->GetActorTransform().InverseTransformPosition(Head);
        UE_LOG(LogMorphRig, Warning, TEXT("MR_FACING_PROBE face=%s actor=%s actor_forward=%s mesh_rotation=%s camera_location=%s camera_forward=%s"), *Face.ToString(), *Operative->GetActorRotation().ToString(), *Operative->GetActorForwardVector().ToString(), *Mesh->GetRelativeRotation().ToString(), *CaptureCamera->GetActorLocation().ToString(), *CaptureCamera->GetActorForwardVector().ToString());
        if (bNativeProbe)
        {
            SaveOutput(TEXT("MorphCapture/") + CaptureKind + TEXT("/geometry_actor.json"), UMorphAuditLibrary::DescribeSkinnedGeometry(Operative->GetMesh()));
            if (NativeProbeMesh) SaveOutput(TEXT("MorphCapture/") + CaptureKind + TEXT("/geometry_probe.json"), UMorphAuditLibrary::DescribeSkinnedGeometry(NativeProbeMesh));
        }
    }

    if (CaptureKind == TEXT("turntable"))
    {
        if (CaptureFrame == 0)
        {
            Operative->ResetShowcase();
            Anim->RequestClip(TEXT("idle_combat"));
            Operative->SetLOD(0);
        }
        Operative->SetActorRotation(FRotator(0, CaptureFrame * 2.0f, 0));
    }
    else if (CaptureKind == TEXT("motion"))
    {
        switch (CaptureFrame)
        {
        case 0: Operative->ResetShowcase(); break;
        case 60: Operative->RequestClip(TEXT("walk_fr")); break;
        case 120: Operative->RequestClip(TEXT("run_l")); break;
        case 180: Operative->RequestClip(TEXT("sprint_f")); break;
        case 240: Operative->RequestDash(TEXT("f")); break;
        case 300: Operative->RequestBlink(); break;
        case 360:
            Operative->ResetShowcase();
            Anim->RequestClip(TEXT("run_f"));
            Operative->SetAim(20, 5);
            Operative->RequestRanged(true);
            break;
        case 420: Operative->StartChannel(); break;
        case 450: Operative->InterruptChannel(); break;
        case 480: Operative->StartCharge(); break;
        case 510: Operative->ReleaseCharge(); break;
        case 570:
            Operative->ResetShowcase();
            Anim->RequestClip(TEXT("run_fr"));
            Operative->ApplyHit(TEXT("r"));
            break;
        case 630: Operative->Knockdown(true); break;
        case 700: Operative->GetUp(); break;
        case 760: Operative->Die(false); break;
        case 850: Operative->Respawn(); break;
        case 940:
            Operative->ResetShowcase();
            Operative->RequestMelee(2);
            break;
        case 970: Operative->RequestReload(); break;
        case 1030: Operative->RequestDeploy(); break;
        case 1090: Operative->StartUplink(); break;
        case 1150: Operative->FinishUplink(); break;
        case 1180: Operative->RequestTurn(-90.0f); break;
        case 1210: Operative->RequestBlink(); break;
        default: break;
        }
    }
    else if (CaptureFrame == 0 && !bNativeProbe)
    {
        Operative->ResetShowcase();
        Operative->PlayDialogue();
    }

    UpdateCaptureCamera();
    if (CaptureKind == TEXT("face"))
    {
        const FMorphAnimSnapshot Timing = Anim->GetSnapshot();
        UE_LOG(LogMorphRig, Warning, TEXT("MR_FACE_TIMING frame=%d delta=%.6f capture_step=%.6f clip=%s clip_time=%.6f duration=%.6f rate_scale=%.5f"), CaptureFrame, DeltaSeconds, Anim->GetCaptureStepSeconds(), *Timing.MainClip.ToString(), Timing.MainTime, Timing.MainDuration, Anim->GetSequence(Timing.MainClip) ? Anim->GetSequence(Timing.MainClip)->RateScale : -1.0f);
    }
    const FString Directory = FPaths::ProjectSavedDir() / TEXT("MorphRig/MorphCapture") / CaptureKind;
    IFileManager::Get().MakeDirectory(*Directory, true);
    const FString Filename = Directory / FString::Printf(TEXT("frame_%04d"), CaptureFrame);
    FScreenshotRequest::RequestScreenshot(Filename, true, false, false, FIntRect(), true);
    ++CaptureFrame;
}

void AMorphGameMode::TickBenchmark(const float DeltaSeconds)
{
    if (bFinishing) return;
    if (BenchmarkPhase >= 4)
    {
        FinishBenchmark();
        return;
    }
    const double Now = FPlatformTime::Seconds();
    if (!bPhaseStarted)
    {
        bPhaseStarted = true;
        PhaseClock = 0.0f;
        LastFrameSeconds = Now;
        if (BenchmarkPhase == 0) SetInstanceCount(1);
        if (BenchmarkPhase == 2) SetInstanceCount(10);
        if (BenchmarkPhase == 1) BenchmarkSamples[0].Empty();
        if (BenchmarkPhase == 3) BenchmarkSamples[1].Empty();
        return;
    }
    const double WallDelta = FMath::Max(0.0, Now - LastFrameSeconds);
    LastFrameSeconds = Now;
    PhaseClock += static_cast<float>(WallDelta);
    const bool bWarmup = BenchmarkPhase == 0 || BenchmarkPhase == 2;
    if (bWarmup && PhaseClock >= 3.0f)
    {
        ++BenchmarkPhase;
        bPhaseStarted = false;
        return;
    }
    if (!bWarmup)
    {
        FMorphBenchmarkSample Sample;
        Sample.FrameMs = WallDelta * 1000.0;
        if (UGameViewportClient* Viewport = GetWorld()->GetGameViewport())
        {
            if (FStatUnitData* Stats = Viewport->GetStatUnitData())
            {
                Sample.GameMs = Stats->RawGameThreadTime;
                Sample.RenderMs = Stats->RawRenderThreadTime;
                Sample.GpuMs = Stats->RawGPUFrameTime[0];
                Sample.GpuMemory = Stats->RawGPUMemoryUsage[0];
            }
        }
        Sample.UsedPhysical = FPlatformMemory::GetStats().UsedPhysical;
        BenchmarkSamples[BenchmarkPhase == 1 ? 0 : 1].Add(Sample);
        if (PhaseClock >= 8.0f)
        {
            ++BenchmarkPhase;
            bPhaseStarted = false;
        }
    }
}

void AMorphGameMode::FinishBenchmark()
{
    if (bFinishing) return;
    bFinishing = true;
    FString Json = FString::Printf(TEXT("{\n\"engine\":\"%s\",\n\"resolution\":\"1920x1080\",\n\"frame_generation\":false,\n\"rhi\":\"%s\",\n\"cpu\":\"%s\",\n\"cpu_cores\":%d,\n\"ram_total_gib\":%d,\n\"gpu\":\"%s\",\n\"gpu_driver\":\"%s\",\n\"samples\":{\n"),
        *FEngineVersion::Current().ToString(), GDynamicRHI ? GDynamicRHI->GetName() : TEXT("unknown"),
        *FPlatformMisc::GetCPUBrand(), FPlatformMisc::NumberOfCores(), FPlatformMemory::GetConstants().TotalPhysicalGB,
        *FString(GRHIAdapterName), *FString(GRHIAdapterUserDriverVersion));
    for (int32 Group = 0; Group < 2; ++Group)
    {
        const TArray<FMorphBenchmarkSample>& Samples = BenchmarkSamples[Group];
        TArray<double> Sorted;
        double Sum = 0.0;
        for (const FMorphBenchmarkSample& Sample : Samples) { Sorted.Add(Sample.FrameMs); Sum += Sample.FrameMs; }
        Sorted.Sort();
        const double Average = Sorted.Num() ? Sum / Sorted.Num() : 0.0;
        const double Median = Sorted.Num() ? Sorted[Sorted.Num() / 2] : 0.0;
        const double P95 = Sorted.Num() ? Sorted[FMath::Min(Sorted.Num() - 1, FMath::FloorToInt(Sorted.Num() * .95))] : 0.0;
        Json += FString::Printf(TEXT("\"%s\":{\"instances\":%d,\"warmup_seconds\":3,\"sample_seconds\":8,\"frame_count\":%d,\"average_ms\":%.4f,\"median_ms\":%.4f,\"p95_ms\":%.4f,\"average_fps\":%.3f,\"frames\":["),
            Group == 0 ? TEXT("one") : TEXT("ten"), Group == 0 ? 1 : 10, Samples.Num(), Average, Median, P95, Average > 0.0 ? 1000.0 / Average : 0.0);
        for (int32 Index = 0; Index < Samples.Num(); ++Index)
        {
            const FMorphBenchmarkSample& Sample = Samples[Index];
            Json += FString::Printf(TEXT("%s[%.4f,%.4f,%.4f,%.4f,%llu,%llu]"), Index ? TEXT(",") : TEXT(""), Sample.FrameMs, Sample.GameMs, Sample.RenderMs, Sample.GpuMs, Sample.UsedPhysical, Sample.GpuMemory);
        }
        Json += TEXT("]}");
        Json += Group == 0 ? TEXT(",") : TEXT("");
    }
    Json += TEXT("}}\n");
    SaveOutput(TEXT("MorphBenchmark/frame_times.json"), Json);
    FPlatformMisc::RequestExitWithStatus(true, 0);
}
