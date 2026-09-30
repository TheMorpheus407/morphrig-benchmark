#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "MorphRig.generated.h"

class UAnimSequence;
class UCameraComponent;
class UAudioComponent;
class UStaticMeshComponent;
class USoundWave;
class SWidget;
class SVerticalBox;
class SScrollBox;
class UMaterialInstanceDynamic;

UCLASS()
class MORPHRIG_API UMorphMarker : public UAnimNotify {
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="MorphRig") FString MarkerName;
    virtual FString GetNotifyName_Implementation() const override {return MarkerName;}
};

struct FMorphEvent { FString Name; float Time=0; };
struct FMorphClip {
    FString Id, Layer, RootPolicy, Form;
    float Duration=1, NominalSpeed=0; bool Loop=false;
    TArray<FMorphEvent> Events;
};

UCLASS()
class MORPHRIG_API UMorphAnimInstance : public UAnimInstance {
    GENERATED_BODY()
public:
    UMorphAnimInstance();
protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override;
};

UCLASS()
class MORPHRIG_API AMorphOperative : public ACharacter {
    GENERATED_BODY()
public:
    AMorphOperative();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    void Request(const FString& Id, bool FromBrowser=false);
    void ResetOperative();
    void StopAction(bool Interrupt);
    void Emit(const FString& Name, const FString& Id, float At);
    UAnimSequence* Sequence(const FString& Id) const;
    const FMorphClip* Clip(const FString& Id) const;
    bool IsTerminal() const;
    bool TranslationAllowed() const;
    void UpdateFace(float Dt);
    void SetTeam(bool Alternate);
    UPROPERTY() class AMorphShowroom* Room=nullptr;
    UPROPERTY() UAudioComponent* Voice=nullptr;
    UPROPERTY() UStaticMeshComponent* Cell=nullptr;
    UPROPERTY() UStaticMeshComponent* Beacon=nullptr;
    UPROPERTY() UStaticMeshComponent* AccentIcon=nullptr;
    UPROPERTY() TArray<UMaterialInstanceDynamic*> DynamicMaterials;
    FString BaseId="idle_relaxed", PreviousBaseId="idle_relaxed", ActionId, PreviousActionId, HitId;
    float BaseTime=0, PreviousBaseTime=0, BaseBlend=1, ActionTime=0, PreviousActionTime=0, ActionBlend=1, HitTime=0;
    float SmoothAimYaw=0, SmoothAimPitch=0, SmoothAimWeight=0;
    float ActionRate=1, AimYaw=0, AimPitch=0, AimWeight=0, FaceWeight=0, Facing=0, FootOffsetL=0, FootOffsetR=0;
    FVector FootNormalL=FVector::UpVector, FootNormalR=FVector::UpVector;
    FVector LastVelocity=FVector::ZeroVector;
    FVector ActionOrigin=FVector::ZeroVector;
    float GroundHeightL=0,GroundHeightR=0;
    float JumpClock=0, LastAirVelocity=0, EventFlash=0, PelvisCorrection=0;
    FString LastEvent="ready", Disable="none", FacePreset="neutral";
    bool BrowserMode=false, Wounded=false, Stasis=false, TeamB=false, ShowBones=false, Paused=false;
    bool CellInHand=false, BeaconReleased=false, Dead=false, BlinkTeleported=false;
    uint64 ActionGeneration=0; int32 LoopCounter=0, InstanceNumber=0;
    TSet<FString> FiredEvents;
    TMap<FString,float> FaceControls;
    TMap<FString,float> FaceLast;
    void SetLocomotion(const FString& Id);
    void AdvanceEvents(const FString& Id,float Old,float Now,bool Wrap);
    void FinishAction(const FString& Completed);
};

UCLASS()
class MORPHRIG_API AMorphController : public APlayerController {
    GENERATED_BODY()
public:
    AMorphController();
    virtual void PlayerTick(float DeltaTime) override;
    virtual void SetupInputComponent() override;
    UPROPERTY() class AMorphShowroom* Room=nullptr;
    void KeyAction(FKey Key);
};

UCLASS()
class MORPHRIG_API AMorphShowroom : public AActor {
    GENERATED_BODY()
public:
    AMorphShowroom();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    UPROPERTY() UCameraComponent* Camera=nullptr;
    UPROPERTY() AMorphOperative* Hero=nullptr;
    UPROPERTY() TArray<AMorphOperative*> Operatives;
    UPROPERTY() TMap<FString,UAnimSequence*> Sequences;
    UPROPERTY() USoundWave* Dialogue=nullptr;
    UPROPERTY() TArray<UStaticMeshComponent*> Targets;
    UPROPERTY() UMaterialInstanceDynamic* StageMaterial=nullptr;
    TMap<FString,FMorphClip> Clips;
    TArray<FString> ClipOrder, MorphNames;
    TMap<FString,TArray<FVector2D>> FaceCurves;
    TMap<FString,TMap<FString,TArray<FVector2D>>> FaceClipCurves;
    TArray<TSharedPtr<class FJsonValue>> FacialFrames;
    int32 CameraMode=0, LOD=0, DemoStep=-1, RequestedCount=1;
    float Elapsed=0, DemoClock=0, CameraOrbit=0, QuitAfter=0, ScreenshotAt=-1, NextFrameCapture=0, CaptureFPS=30;
    bool Demo=false, UIVisible=true, ShowNormals=false, MovableTargets=false, TerrainDemo=false;
    int32 TerrainStage=-1;
    FString CaptureMode, Filter, LastTrace, TraceText, FrameCSV, CaptureDir, EvidenceDir;
    TSharedPtr<SWidget> Panel;
    TSharedPtr<SScrollBox> BrowserList;
    TSharedPtr<SVerticalBox> FaceList;
    void LoadData();
    void BuildRoom();
    void BuildUI();
    void RebuildBrowser();
    void ToggleCount();
    void SetLOD(int32 L);
    void SetCamera(int32 Mode);
    void StartDemo();
    void Trace(const FString& Text);
    void SelectClip(const FString& Id);
    void SetFacePreset(const FString& Preset);
    void SetDisable(const FString& State);
    void ApplyMaterialMode();
    FString Status() const;
    void SaveLogs();
    void TakeScreenshot(const FString& Name);
};

UCLASS()
class MORPHRIG_API AMorphGameMode : public AGameModeBase {
    GENERATED_BODY()
public:
    AMorphGameMode();
    virtual void BeginPlay() override;
};
