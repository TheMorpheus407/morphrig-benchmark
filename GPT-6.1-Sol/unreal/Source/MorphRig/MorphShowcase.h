#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "MorphShowcase.generated.h"

class AMorphOperative;
class ACameraActor;
class AStaticMeshActor;

struct FMorphBootVertex
{
    int32 Side = 0, Vertex = 0;
    TArray<int32> Bones;
    TArray<FVector> BoneLocalPositions;
    TArray<double> Weights;
};

UCLASS()
class MORPHRIG_API AMorphShowcaseMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AMorphShowcaseMode();
    virtual void BeginPlay() override;
};

UCLASS()
class MORPHRIG_API AMorphShowcaseController : public APlayerController
{
    GENERATED_BODY()
public:
    virtual void BeginPlay() override;
    virtual void PlayerTick(float Delta) override;
    void ApplyStartupOptions();
    virtual bool InputKey(const FInputKeyEventArgs& Params) override;
    void SetView(int32 Mode);
    void ToggleInstances();
    void StartSequence();
    void StepSequence(float Delta);
    void MoveTarget();
    void SelectClip(FName Id);
    TArray<FName> FilteredClips() const;
    void StartPerfCapture();
    void FinishPerfCapture();
    void RecordTerrainSample();
    void LoadBootSurface();
    void Click(FName Name);
    UPROPERTY() TObjectPtr<AMorphOperative> Operative;
    UPROPERTY() TObjectPtr<ACameraActor> ShowCamera;
    UPROPERTY() TArray<TObjectPtr<AMorphOperative>> Crowd;
    UPROPERTY() TArray<TObjectPtr<AStaticMeshActor>> Targets;
    bool bBrowser = false, bFacePanel = false, bHelp = true, bSequence = false;
    bool bPerf = false, bNormalMovement = true, bTargetAim = false;
    bool bNoHUD = false, bTurntable = false, bSweep = false;
    bool bTeamIcons = true;
    bool bTerrain = false, bTerrainSteps = false;
    float TerrainTime = 0, TerrainSampleTime = 0;
    FString TerrainCSV;
    TArray<FMorphBootVertex> BootVertices;
    FString Search;
    int32 BrowserPage = 0, FacePage = 0, FaceSelection = 0, ViewMode = 0;
    float SequenceTime = 0, PerfTime = 0, Orbit = 0, CameraDistance = 550;
    float Elapsed = 0, ExitSeconds = 0, ScreenshotAt = -1, SweepTime = 0;
    float StartDelay = 0;
    bool bWaitingToStart = false, bPendingSequence = false, bPendingTurntable = false, bStartupApplied = false;
    FName PendingClip,PendingAction;
    int32 SweepIndex = -1;
    int32 SequenceStep = 0;
    TArray<double> FrameMs;
    TArray<double> GameMs, RenderMs, GPUms;
    FString PerformancePath;
};

UCLASS()
class MORPHRIG_API AMorphShowcaseHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
    virtual void NotifyHitBoxClick(FName BoxName) override;
    void Label(const FString& Value, float X, float Y, float Scale = 1, FLinearColor Color = FLinearColor::White);
    void Button(FName Id, const FString& Caption, float X, float Y, float W, float H, bool Active = false);
};
